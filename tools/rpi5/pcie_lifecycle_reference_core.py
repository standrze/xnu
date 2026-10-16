# SPDX-License-Identifier: BSD-2-Clause
"""Read-only Linux lifecycle reference; never XNU admission or an IRQ mask.

The existing PCIe reference module is supplied explicitly. Remote execution
embeds both sources in memory; no helper is installed on the Pi. Property
filtering precedes reads. No /chosen, seed, identity, raw MMIO or config write.
"""
import datetime
from pathlib import Path
import re
import struct

PCIE1 = "/axi/pcie@1000110000"
PCIE2 = "/axi/pcie@1000120000"
MIP1 = "/axi/msi-controller@1000131000"
XOSC = "/clocks/clk_xosc"
GIC = "/soc@107c000000/interrupt-controller@7fff9000"
EXTRA_PROPERTIES = {
    PCIE1: ("compatible", "status", "reg", "clocks", "clock-names",
            "power-domains", "resets", "reset-names", "msi-parent",
            "interrupt-parent", "interrupts", "interrupts-extended"),
    PCIE2: ("power-domains", "iommus", "iommu-map", "brcm,enable-ssc",
            "brcm,tperst-clk-ms", "brcm,scb-sizes", "brcm,clkreq-mode",
            "aspm-no-l0s", "brcm,fifo-qos-map", "brcm,vdm-qos-map"),
    MIP1: ("compatible", "reg", "phandle", "msi-controller", "msi-ranges",
           "brcm,msi-offset"),
    XOSC: ("compatible", "phandle", "#clock-cells", "clock-frequency"),
    GIC: ("reg",),
    PCIE2 + "/rp1/clocks@18000": ("assigned-clocks", "assigned-clock-rates"),
}
PCI_DEVICES = ("0001:00:00.0", "0001:01:00.0", "0002:00:00.0", "0002:01:00.0")
POWER_PATHS = {
    **{bdf: "/sys/bus/pci/devices/" + bdf for bdf in PCI_DEVICES},
    "pcie1-host": "/sys/bus/platform/devices/1000110000.pcie",
    "pcie2-host": "/sys/bus/platform/devices/1000120000.pcie",
}
CLOCK_NAMES = frozenset(("xosc", "pll_sys_core", "pll_sys", "pll_sys_sec",
                         "clk_sys", "clk_eth", "clk_eth_tsu"))
OPERATIONS = {"raw_mmio_accesses": 0, "pci_config_writes": 0, "sd_actions": 0,
              "driver_changes": 0, "mount_changes": 0, "network_changes": 0, "reboots": 0}
LIMITATIONS = {"xnu_admission": False, "irq_masking_proven": False,
               "dma_quiescence_proven": False, "power_clock_ownership_proven": False,
               "watchdog_reset_return_proven": False, "ethernet_proven": False}


def collect_extra(read_property):
    result = {}
    for node, names in EXTRA_PROPERTIES.items():
        result[node] = {}
        for name in names:
            try:
                data = read_property(node, name)
            except FileNotFoundError:
                data = None
            if data is not None and (not isinstance(data, bytes) or len(data) > 4096):
                raise ValueError("oversized or invalid lifecycle property")
            result[node][name] = None if data is None else data.hex()
    return result


def validate_extra(properties):
    if not isinstance(properties, dict) or set(properties) != set(EXTRA_PROPERTIES):
        raise ValueError("unallowlisted or missing lifecycle nodes")
    for node, names in EXTRA_PROPERTIES.items():
        fields = properties[node]
        if not isinstance(fields, dict) or set(fields) != set(names):
            raise ValueError("unallowlisted or missing lifecycle properties")
        for value in fields.values():
            if value is not None and (not isinstance(value, str) or len(value) > 8192 or
                                      len(value) % 2 or not re.fullmatch(r"[0-9a-f]*", value)):
                raise ValueError("invalid lifecycle property encoding")


def clock_rows(text):
    """Decode the observed clk_summary table, retaining only selected rows.

    Consumer continuation lines do not begin with a clock plus numeric counts.
    Unknown column layout is refused, not interpreted as clocks being absent.
    This debugfs format is a reference format, not a stable kernel ABI.
    """
    lines = text.splitlines()
    if (len(text) > 131072 or len(lines) < 3 or
            lines[1].split()[:4] != ["clock", "count", "count", "count"] or
            lines[1].split()[4:9] != ["rate", "accuracy", "phase", "cycle", "enable"]):
        raise ValueError("unsupported or oversized Linux clock summary")
    result = {}
    total = 0
    for line in lines[3:]:
        fields = line.split()
        if len(fields) < 9 or not all(re.fullmatch(r"[0-9]+", v) for v in fields[1:8]):
            continue
        total += 1
        name = fields[0]
        if name not in CLOCK_NAMES and not any(token in name.lower() for token in ("pcie", "rescal")):
            continue
        if name in result or fields[8] not in ("Y", "N", "?") or len(name) > 128:
            raise ValueError("invalid or duplicate selected clock")
        result[name] = dict(zip(("enable_count", "prepare_count", "protect_count", "rate_hz",
                                 "accuracy", "phase", "duty_cycle"), map(int, fields[1:8])))
        result[name]["hardware_enable"] = fields[8]
    if not total:
        raise ValueError("empty or unrecognized Linux clock summary")
    return {"status": "read", "framework_clock_rows": total, "selected": result}


def interrupt_rows(text):
    lines = text.splitlines()
    cpus = lines[0].split() if lines else []
    if not 1 <= len(cpus) <= 4 or cpus != ["CPU" + str(i) for i in range(len(cpus))]:
        raise ValueError("unsupported interrupt CPU header")
    result = []
    for line in lines[1:]:
        fields = line.split()
        if not fields or not re.fullmatch(r"[0-9]+:", fields[0]):
            continue
        n = len(cpus)
        if len(fields) < n + 5 or not all(re.fullmatch(r"[0-9]+", v) for v in fields[1:n+1]):
            raise ValueError("malformed numbered interrupt")
        chip, raw, trigger = fields[n+1:n+4]
        if not re.fullmatch(r"[0-9]+", raw):
            raise ValueError("unsupported interrupt hardware number")
        hwirq = int(raw)
        relevant = ((chip == "GICv2" and (160 <= hwirq <= 266)) or
                    chip == "rp1_irq_chip" or
                    chip.startswith("MIP-MSI-PCI-MSIX-0001:01:00.0") or
                    chip.startswith("MIP-MSI-PCI-MSIX-0002:01:00.0"))
        if relevant:
            result.append({"linux_irq": int(fields[0][:-1]), "chip": chip, "hwirq": hwirq,
                           "trigger": trigger, "actions": " ".join(fields[n+4:]),
                           "cpu_counts": list(map(int, fields[1:n+1]))})
    if len(result) > 256 or len({row["linux_irq"] for row in result}) != len(result):
        raise ValueError("duplicate or excessive relevant interrupts")
    return result


def linux_extra(reference):
    def property_read(node, name):
        return reference.read_bounded(Path("/proc/device-tree") / node.lstrip("/") / name, 4096)

    def optional(path, maximum=4096):
        try:
            return reference.read_bounded(Path(path), maximum).decode().strip()
        except FileNotFoundError:
            return None  # Missing ABI file is not a power/clock success.

    power = {}
    for name, path in POWER_PATHS.items():
        power[name] = {key: optional(path + "/power/" + key, 128)
                       for key in ("runtime_status", "control")}
    links = {bdf: {key: optional("/sys/bus/pci/devices/" + bdf + "/" + key, 128)
                   for key in ("current_link_speed", "current_link_width")}
             for bdf in ("0001:01:00.0", "0002:01:00.0")}
    summary = optional("/sys/kernel/debug/clk/clk_summary", 131072)
    clocks = {"status": "unavailable", "selected": {}} if summary is None else clock_rows(summary + "\n")
    # Only existing metadata paths are read; no debugfs mount or IRQ request.
    interrupts = interrupt_rows(reference.read_bounded(Path("/proc/interrupts"), 131072).decode())
    msi = {}
    for bdf in ("0001:01:00.0", "0002:01:00.0"):
        directory = Path("/sys/bus/pci/devices") / bdf / "msi_irqs"
        entries = sorted(directory.iterdir(), key=lambda p: p.name)
        if len(entries) > 64 or any(not re.fullmatch(r"[0-9]+", p.name) for p in entries):
            raise ValueError("unexpected MSI allocation metadata")
        msi[bdf] = {p.name: reference.read_bounded(p, 16).decode().strip() for p in entries}
    return {"of_properties_hex": collect_extra(property_read), "power": power,
            "links": links, "clocks": clocks, "interrupts": interrupts, "msi_allocations": msi}


def stable_snapshot(snapshot):
    # IRQ counts may increase on live Linux. Routes must not change. Preserve
    # both count samples as evidence without requiring an idle SSD system.
    result = dict(snapshot)
    result["interrupts"] = [{k: v for k, v in row.items() if k != "cpu_counts"}
                            for row in snapshot["interrupts"]]
    return result


def cells(properties, node, name):
    value = properties[node][name]
    if value is None or len(value) % 8:
        raise ValueError("missing or malformed cell property: " + node + "/" + name)
    raw = bytes.fromhex(value)
    return list(struct.unpack(">" + "I" * (len(raw) // 4), raw))


def gic_spi(spec, expected_flags):
    if len(spec) != 3 or spec[0] != 0 or not 0 <= spec[1] < 988 or spec[2] != expected_flags:
        raise ValueError("unsupported GIC SPI declaration")
    return 32 + spec[1]


def decode_dependencies(reference_report, extra, reference):
    reference.validate_capture(reference_report)
    props = reference_report["first"]["of_properties_hex"]
    more = extra["of_properties_hex"]
    validate_extra(more)
    gic = cells(props, GIC, "phandle")
    reset = "/soc@107c000000/reset-controller@1504318"
    rescal = "/soc@107c000000/reset-controller@119500"
    if len(gic) != 1 or not 0 < gic[0] < 0xffffffff or cells(props, reset, "#reset-cells") != [1] or cells(props, rescal, "#reset-cells") != [0]:
        raise ValueError("unsupported parent cell geometry")
    one = cells(more, PCIE1, "resets")
    two = cells(props, PCIE2, "resets")
    common = cells(props, rescal, "phandle") + cells(props, reset, "phandle")
    if one != common + [43] or two != common + [44]:
        raise ValueError("not the same shared RESCAL and distinct bridge reset declarations")
    if (more[PCIE1]["compatible"] != b"brcm,bcm2712-pcie\0".hex() or
            more[PCIE1]["status"] != b"okay\0".hex() or
            more[PCIE1]["reset-names"] != b"rescal\0bridge\0".hex() or
            cells(more, PCIE1, "reg") != [0x10, 0x110000, 0, 0x9310]):
        raise ValueError("unsupported shared-controller declaration")
    if (cells(props, PCIE2, "interrupt-parent") != gic or
            cells(more, PCIE1, "interrupt-parent") != gic or
            more[PCIE1]["interrupts-extended"] is not None):
        raise ValueError("unsupported controller IRQ parent/override")
    irq = cells(props, PCIE2, "interrupts")
    if len(irq) != 6:
        raise ValueError("unsupported controller interrupt count")
    direct = [gic_spi(irq[i:i+3], 4) for i in (0, 3)]
    mapping = cells(props, PCIE2, "interrupt-map")
    intx = []
    if len(mapping) != 32:
        raise ValueError("unsupported INTx interrupt map")
    for i in range(4):
        row = mapping[8*i:8*i+8]
        if row[:5] != [0, 0, 0, i+1, gic[0]]:
            raise ValueError("unsupported INTx mapping/parent")
        intx.append(gic_spi(row[5:], 4))
    mip = "/axi/msi-controller@1000130000"
    msi = cells(props, mip, "msi-ranges")
    if len(msi) != 5 or msi[0] != gic[0] or not 1 <= msi[-1] <= 64:
        raise ValueError("unsupported MIP GIC range")
    first = gic_spi(msi[1:4], 1)
    if first + msi[4] > 1020:
        raise ValueError("MIP GIC range overflow")
    if cells(props, PCIE2, "msi-parent") != cells(props, mip, "phandle"):
        raise ValueError("wrong PCIe2 MSI parent")
    if cells(more, PCIE1, "msi-parent") != cells(more, MIP1, "phandle"):
        raise ValueError("wrong shared-controller MSI parent")
    nvme_msi = cells(more, MIP1, "msi-ranges")
    if len(nvme_msi) != 5 or nvme_msi[0] != gic[0] or not 1 <= nvme_msi[-1] <= 64:
        raise ValueError("unsupported shared-controller MIP GIC range")
    nvme_first = gic_spi(nvme_msi[1:4], 1)
    if nvme_first + nvme_msi[4] > 1020:
        raise ValueError("shared-controller MIP GIC range overflow")
    nvme_irq = cells(more, PCIE1, "interrupts")
    if len(nvme_irq) != 6:
        raise ValueError("unsupported shared-controller interrupt count")
    nvme_direct = [gic_spi(nvme_irq[i:i+3], 4) for i in (0, 3)]
    clock = PCIE2 + "/rp1/clocks@18000"
    frequency = cells(more, XOSC, "clock-frequency")
    if (len(frequency) != 1 or not frequency[0] or
            cells(props, clock, "clocks") != cells(more, XOSC, "phandle") or
            cells(more, XOSC, "#clock-cells") != [0] or
            more[XOSC]["compatible"] != b"fixed-clock\0".hex()):
        raise ValueError("unsupported RP1 oscillator binding")
    gem = PCIE2 + "/rp1/ethernet@100000"
    names = bytes.fromhex(props[gem]["clock-names"]).split(b"\0")
    clocks = cells(props, gem, "clocks")
    handle = cells(props, clock, "phandle")[0]
    if names != [b"pclk", b"hclk", b"tsu_clk", b"tx_clk", b""] or len(clocks) != 8:
        raise ValueError("unsupported GEM clock names/arity")
    if any(clocks[i] != handle for i in (0, 2, 4, 6)):
        raise ValueError("GEM clock provider differs")
    target = sorted(set(intx + direct + list(range(first, first+msi[4]))))
    nvme_interrupts = nvme_direct + list(range(nvme_first, nvme_first+nvme_msi[4]))
    if set(target).intersection(nvme_interrupts):
        raise ValueError("PCIe2 IRQ plan overlaps the shared-controller/NVMe routes")
    # A read-only future GIC snapshot needs these banks, not blanket masking
    # that would touch PCIe1/NVMe's adjacent interrupt bits.
    masks = {}
    for irq in target:
        bank = irq // 32
        masks[bank] = masks.get(bank, 0) | 1 << (irq % 32)
    return {"shared_rescal_phandle": common[0], "bridge_reset_ids": [one[-1], two[-1]],
            "pcie2_direct_gic_intids": direct, "pcie2_intx_gic_intids": intx,
            "pcie2_mip_gic_intids": [first, first+msi[4]-1],
            "pcie2_gic_bank_masks": {str(k): f"0x{v:08x}" for k, v in masks.items()},
            "pcie1_direct_gic_intids": nvme_direct,
            "pcie1_mip_gic_intids": [nvme_first, nvme_first+nvme_msi[4]-1],
            "pcie1_controller_clock_declared": more[PCIE1]["clocks"] is not None,
            "pcie2_controller_clock_declared": props[PCIE2]["clocks"] is not None,
            "pcie1_power_domain_declared": more[PCIE1]["power-domains"] is not None,
            "pcie2_power_domain_declared": more[PCIE2]["power-domains"] is not None,
            "rp1_oscillator_hz": frequency[0],
            "gem_clock_ids": {name.decode(): clocks[2*i+1] for i, name in enumerate(names[:-1])}}


def validate_snapshot(sample):
    if set(sample) != {"of_properties_hex", "power", "links", "clocks", "interrupts", "msi_allocations"}:
        raise ValueError("wrong lifecycle snapshot fields")
    validate_extra(sample["of_properties_hex"])
    if set(sample["power"]) != set(POWER_PATHS):
        raise ValueError("missing runtime-power paths")
    for row in sample["power"].values():
        if (set(row) != {"control", "runtime_status"} or
                row["control"] not in (None, "auto", "on") or
                row["runtime_status"] not in (None, "active", "suspended", "suspending", "resuming", "unsupported", "error")):
            raise ValueError("malformed power observation")
    endpoints = {"0001:01:00.0", "0002:01:00.0"}
    if set(sample["links"]) != endpoints or set(sample["msi_allocations"]) != endpoints:
        raise ValueError("missing PCI endpoint observations")
    for row in sample["links"].values():
        if (set(row) != {"current_link_speed", "current_link_width"} or
                any(v is not None and (not isinstance(v, str) or len(v) > 128) for v in row.values())):
            raise ValueError("malformed link metadata")
    for allocations in sample["msi_allocations"].values():
        if len(allocations) > 64 or any(not re.fullmatch(r"[0-9]+", k) or v not in ("msi", "msix") for k, v in allocations.items()):
            raise ValueError("malformed MSI allocations")
    clocks = sample["clocks"]
    if clocks.get("status") == "unavailable":
        if clocks != {"status": "unavailable", "selected": {}}:
            raise ValueError("unavailable clock summary has fabricated values")
    elif clocks.get("status") == "read":
        if (set(clocks) != {"status", "selected", "framework_clock_rows"} or
                type(clocks["framework_clock_rows"]) is not int or not 1 <= clocks["framework_clock_rows"] <= 2048 or
                len(clocks["selected"]) > clocks["framework_clock_rows"]):
            raise ValueError("invalid clock summary bounds")
        numeric = {"enable_count", "prepare_count", "protect_count", "rate_hz", "accuracy", "phase", "duty_cycle"}
        for name, row in clocks["selected"].items():
            if (len(name) > 128 or not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or
                    (name not in CLOCK_NAMES and not any(t in name.lower() for t in ("pcie", "rescal"))) or
                    set(row) != numeric | {"hardware_enable"} or row["hardware_enable"] not in ("Y", "N", "?") or
                    any(type(row[k]) is not int or not 0 <= row[k] < 1 << 64 for k in numeric)):
                raise ValueError("invalid selected clock observation")
    else:
        raise ValueError("missing clock capture status")
    interrupts = sample["interrupts"]
    if not isinstance(interrupts, list) or len(interrupts) > 256:
        raise ValueError("invalid IRQ observation list")
    seen = set()
    for row in interrupts:
        if set(row) != {"linux_irq", "chip", "hwirq", "trigger", "actions", "cpu_counts"}:
            raise ValueError("invalid IRQ observation fields")
        counts = row["cpu_counts"]
        if (any(type(row[k]) is not int or not 0 <= row[k] < 1 << 32 for k in ("linux_irq", "hwirq")) or
                row["linux_irq"] in seen or row["trigger"] not in ("Level", "Edge") or
                any(not isinstance(row[k], str) or len(row[k]) > 256 for k in ("chip", "actions")) or
                not isinstance(counts, list) or not 1 <= len(counts) <= 4 or
                any(type(v) is not int or not 0 <= v < 1 << 64 for v in counts)):
            raise ValueError("invalid IRQ observation/counts")
        seen.add(row["linux_irq"])


def validate_lifecycle(report, reference):
    if report.get("schema_version") != 1 or report.get("status") != "linux_reference_only":
        raise ValueError("wrong lifecycle reference schema/status")
    if report.get("operations") != OPERATIONS or any(type(v) is not int for v in report["operations"].values()):
        raise ValueError("wrong lifecycle operation profile")
    if report.get("limitations") != LIMITATIONS or any(type(v) is not bool for v in report["limitations"].values()):
        raise ValueError("Linux metadata does not admit XNU hardware")
    old = report["reference"]
    reference.validate_capture(old)
    if old["identity_before"] != report.get("identity_after"):
        raise ValueError("Linux identity changed across lifecycle capture")
    first, second = report["first"], report["second"]
    validate_snapshot(first)
    validate_snapshot(second)
    if stable_snapshot(first) != stable_snapshot(second):
        raise ValueError("lifecycle metadata changed between snapshots; do not retry implicitly")
    return decode_dependencies(old, first, reference)


def capture_lifecycle(reference):
    old = reference.capture_linux()
    first = linux_extra(reference)
    second = linux_extra(reference)
    report = {"schema_version": 1, "status": "linux_reference_only", "reference": old,
              "first": first, "second": second, "identity_after": reference.linux_identity(),
              "operations": dict(OPERATIONS), "limitations": dict(LIMITATIONS),
              "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    validate_lifecycle(report, reference)
    return report
