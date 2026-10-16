# SPDX-License-Identifier: BSD-2-Clause
"""Exact runtime identity replay; never substitutes for fresh boot admission."""
import re


def validate(raw, receipt):
    lines = raw.replace(b'\r', b'').splitlines()
    actual = [line.decode('ascii') for line in lines if line.startswith(b'ROOTIDENTITY:')]
    expected = ['ROOTIDENTITY:BEGIN:FIXED_CATALOG_V1',
                'ROOTIDENTITY:MOUNT:mockfs:/:READONLY:NODES='+str(receipt['output_nodes'])+
                ':BYTES='+str(receipt['output_bytes'])]
    rows = receipt['identity_catalog']
    if len(rows) != receipt['output_nodes'] or len({row['path'] for row in rows}) != len(rows):
        raise ValueError('Invalid identity catalog')
    for row in rows:
        if row['path']=='/dev' and row['mode']==0o40555 and row['bytes']==0 and row['sha256']=='':
            expected.append('ROOTIDENTITY:OVERLAY:/dev:devfs')
        elif row['mode'] & 0o170000 == 0o40000:
            if row['bytes'] or row['sha256'] != '':
                raise ValueError('Invalid directory catalog')
            expected.append('ROOTIDENTITY:DIR:'+row['path']+':MODE='+str(row['mode']))
        elif row['mode'] & 0o170000 == 0o100000 and re.fullmatch('[0-9a-f]{64}', row['sha256'] or ''):
            expected.append('ROOTIDENTITY:FILE:'+row['path']+':MODE='+str(row['mode'])+
                            ':BYTES='+str(row['bytes'])+':SHA256='+row['sha256'])
        else:
            raise ValueError('Invalid file catalog')
    expected.append('ROOTIDENTITY:PASS:COMPARE_SELF_AND_EXTENT_EXTERNALLY')
    if actual != expected:
        raise ValueError('Mounted-root identity output differs from installed catalog/extent/self hash')
    return dict(mounted_root_runtime_identity=True, self_digest_verified=True,
                filesystem='mockfs', readonly=True, nodes=len(rows),
                bytes=receipt['output_bytes'], file_hashes=sum(bool(row['sha256']) for row in rows),
                covered_archive_dev_node_verified=False,devfs_overlay_verified=True,
                scope='Visible fixed catalog/metadata/contents, devfs overlay and root geometry; not covered /dev bytes, kernel authenticity or durable storage')
