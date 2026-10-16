// SPDX-License-Identifier: BSD-2-Clause
import Foundation
import ProbeSupport
import Virtualization

final class VMRunner: NSObject, VZVirtualMachineDelegate {
    private var machine: VZVirtualMachine?
    private var completed = false
    private var failure: Error?
    private var serial: FileHandle?

    func run(directory: URL, seconds: Int) throws {
        guard Thread.isMainThread, VZVirtualMachine.isSupported else {
            throw ProbeError.invalid("requires a supported Mac and the main thread")
        }
        let configuration = VZVirtualMachineConfiguration()
        configuration.cpuCount = 1
        configuration.memorySize = 512 * 1024 * 1024
        configuration.platform = VZGenericPlatformConfiguration()
        let loader = VZEFIBootLoader()
        loader.variableStore = try VZEFIVariableStore(
            creatingVariableStoreAt: directory.appendingPathComponent("efi-variables.bin"), options: [])
        configuration.bootLoader = loader
        let attachment = try VZDiskImageStorageDeviceAttachment(
            url: directory.appendingPathComponent("disk.img"), readOnly: false)
        configuration.storageDevices = [VZVirtioBlockDeviceConfiguration(attachment: attachment)]
        let log = directory.appendingPathComponent("serial.log")
        try Data().write(to: log, options: .withoutOverwriting)
        let handle = try FileHandle(forWritingTo: log)
        serial = handle
        defer {
            try? handle.close()
            serial = nil
            machine = nil
        }
        let console = VZVirtioConsoleDeviceSerialPortConfiguration()
        console.attachment = VZFileHandleSerialPortAttachment(fileHandleForReading: nil, fileHandleForWriting: handle)
        configuration.serialPorts = [console]
        // No network, host directory shares, socket devices, nested virtualization or GPU.
        try configuration.validate()
        let vm = VZVirtualMachine(configuration: configuration)
        vm.delegate = self
        machine = vm
        vm.start { [weak self] result in
            if case .failure(let error) = result {
                self?.failure = error
                self?.completed = true
            }
        }
        let deadline = ProcessInfo.processInfo.systemUptime + Double(seconds)
        pump(until: deadline)
        if !completed {
            failure = ProbeError.invalid("guest exceeded bounded \(seconds)-second deadline")
            vm.stop { [weak self] error in
                if let error {
                    self?.failure = ProbeError.invalid("guest deadline exceeded; stop failed: \(error)")
                }
                self?.completed = true
            }
            pump(until: ProcessInfo.processInfo.systemUptime + 5)
        }
        if let failure { throw failure }
        guard completed, vm.state == .stopped else { throw ProbeError.invalid("virtual machine did not stop") }
    }

    private func pump(until deadline: TimeInterval) {
        while !completed && ProcessInfo.processInfo.systemUptime < deadline {
            _ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.05))
        }
    }

    func guestDidStop(_ virtualMachine: VZVirtualMachine) {
        completed = true
    }

    func virtualMachine(_ virtualMachine: VZVirtualMachine, didStopWithError error: Error) {
        failure = error
        completed = true
    }
}
