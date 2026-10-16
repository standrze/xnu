/*
 * Copyright (c) 1998-2012 Apple Inc. All rights reserved.
 *
 * @APPLE_OSREFERENCE_LICENSE_HEADER_START@
 *
 * This file contains Original Code and/or Modifications of Original Code
 * as defined in and that are subject to the Apple Public Source License
 * Version 2.0 (the 'License'). You may not use this file except in
 * compliance with the License. The rights granted to you under the License
 * may not be used to create, or enable the creation or redistribution of,
 * unlawful or unlicensed copies of an Apple operating system, or to
 * circumvent, violate, or enable the circumvention or violation of, any
 * terms of an Apple operating system software license agreement.
 *
 * Please obtain a copy of the License at
 * http://www.opensource.apple.com/apsl/ and read it before using this file.
 *
 * The Original Code and all software distributed under the License are
 * distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
 * EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
 * INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
 * Please see the License for the specific language governing rights and
 * limitations under the License.
 *
 * @APPLE_OSREFERENCE_LICENSE_HEADER_END@
 */
/*
 * NOTICE: This file was modified by SPARTA, Inc. in 2005 to introduce
 * support for mandatory and extensible security protections.  This notice
 * is included in support of clause 2.2 (b) of the Apple Public License,
 * Version 2.0.
 */

const char * gIOKernelConfigTables =
    "("
#if defined(ARM64_BOARD_CONFIG_BCM2712) && DEVELOPMENT
    "   {"
    "     'IOClass'         = BCM2712PlatformExpert;"
    "     'IOProviderClass' = IOPlatformExpertDevice;"
    "     'IONameMatch'     = 'device-tree';"
    "     'IOProbeScore'    = 1000:32;"
    "   },"
#if RPI5_STORAGE_PROVIDER
    /* Built-in removable-slot transport and pinned IOStorageFamily matching.
     * Upstream data: IOStorageFamily-337.100.1/Info.plist. Real service code is
     * linked only by --with-storage-provider; startup also requires a boot arg. */
#if RPI5_STORAGE_WRITE_PROVIDER
    "   { 'IOClass'=BCM2712SDWriteStorage; 'IOProviderClass'=IOPlatformDevice;"
#else
    "   { 'IOClass'=BCM2712SDStorage; 'IOProviderClass'=IOPlatformDevice;"
#endif
    "     'IONameMatch'=sdio1; 'IOProbeScore'=1000:32; },"
    "   { 'IOClass'=IOBlockStorageDriver; 'IOProviderClass'=IOBlockStorageDevice;"
    "     'IOPropertyMatch'={ 'device-type'=Generic; }; },"
    "   { 'IOClass'=IOMediaBSDClient; 'IOProviderClass'=IOMedia;"
    "     'IOMatchCategory'=IOMediaBSDClient; 'IOProbeScore'=30000:32;"
    "     'IOResourceMatch'=IOBSD; },"
    "   { 'IOClass'=IOFDiskPartitionScheme; 'IOProviderClass'=IOMedia;"
    "     'IOMatchCategory'=IOStorage; 'IOProbeScore'=3000:32;"
    "     'IOPropertyMatch'={ Whole=.true.; };"
    "     'Content Mask'='FDisk_partition_scheme'; 'Content Table'={"
    "       '0x01'='DOS_FAT_12'; '0x04'='DOS_FAT_16_S'; '0x06'='DOS_FAT_16';"
    "       '0x07'='Windows_NTFS'; '0x0B'='DOS_FAT_32'; '0x0C'='Windows_FAT_32';"
    "       '0x0E'='Windows_FAT_16'; '0x14'='DOS_FAT_16_S_Hidden';"
    "       '0x16'='DOS_FAT_16_Hidden'; '0x42'='Windows_LDM'; '0x82'='Linux_Swap';"
    "       '0x83'='Linux'; '0x8E'='Linux_LVM'; '0xA5'='FreeBSD'; '0xA6'='OpenBSD';"
    "       '0xA7'='Apple_Rhapsody_UFS'; '0xA8'='Apple_UFS'; '0xA9'='NetBSD';"
    "       '0xAB'='Apple_Boot'; '0xAE'='Apple_Encrypted'; '0xAF'='Apple_HFS';"
    "       '0xFD'='Linux_RAID'; }; },"
    /* Built-in services do not inherit kext dependency ordering. Require the
     * converter-ready resource before HFS can register with VFS. Both services
     * also require bcm2712_hfs=1 at start; the SD-only diagnostic stays isolated. */
    "   { 'IOClass'='com_apple_filesystems_hfs_encodings';"
    "     'IOProviderClass'=IOResources;"
    "     'IOMatchCategory'='com_apple_filesystems_hfs_encodings';"
    "     'IOResourceMatch'=IOBSD; },"
    "   { 'IOClass'='com_apple_filesystems_hfs';"
    "     'IOProviderClass'=IOResources;"
    "     'IOMatchCategory'='com_apple_filesystems_hfs';"
    "     'IOResourceMatch'=(IOBSD, 'RPI5HFSEncodingsReady'); },"
#endif
#endif
    "   {"
    "     'IOClass'         = IOPanicPlatform;"
    "     'IOProviderClass' = IOPlatformExpertDevice;"
    "     'IOProbeScore'    = 0:32;"
    "   },"
    "   {"
    "     'IOClass'         = IOExclaveProxy;"
    "     'IOProviderClass' = IOService;"
    "     'IOExclaveProxy'  = 1:32;"
    "   }"
    ")";
