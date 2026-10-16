/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_XNU_API_H
#define RPI5_DISPLAY_XNU_API_H
/* Once published, no framebuffer mapping may be replaced/freed by this
 * bounded candidate. Revocation alone does not quiesce in-flight readers. */
int rpi5_display_xnu_mirror_started(void);
#include <stdint.h>
int rpi5_display_xnu_map_admit(uint64_t,uint64_t,unsigned,unsigned,unsigned);
int rpi5_display_xnu_video_admit(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
int rpi5_display_xnu_mapping_verify(uint64_t,uint64_t,uint64_t);
int rpi5_display_xnu_geometry(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
#endif
