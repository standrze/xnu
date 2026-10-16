/* SPDX-License-Identifier: BSD-2-Clause
 * Built-in VZ transport and matching for pinned Apple storage/HFS services.
 * Classic OSUnserialize strings containing underscores must be quoted.
 */
    " { 'IOClass'=VZBlockStorage; 'IOProviderClass'=IOPlatformDevice; 'IONameMatch'='virtio-block'; 'IOProbeScore'=1000:32; },"
    " { 'IOClass'=IOBlockStorageDriver; 'IOProviderClass'=IOBlockStorageDevice; 'IOPropertyMatch'={ 'device-type'=Generic; }; },"
    " { 'IOClass'=IOMediaBSDClient; 'IOProviderClass'=IOMedia; 'IOMatchCategory'=IOMediaBSDClient; 'IOProbeScore'=30000:32; 'IOResourceMatch'=IOBSD; },"
    " { 'IOClass'='com_apple_filesystems_hfs_encodings'; 'IOProviderClass'=IOResources; 'IOMatchCategory'='com_apple_filesystems_hfs_encodings'; 'IOResourceMatch'=IOBSD; },"
    " { 'IOClass'='com_apple_filesystems_hfs'; 'IOProviderClass'=IOResources; 'IOMatchCategory'='com_apple_filesystems_hfs'; 'IOResourceMatch'=(IOBSD,'VZHFSEncodingsReady'); },"
