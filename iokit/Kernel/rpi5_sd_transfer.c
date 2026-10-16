/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_sd_transfer.h"

struct rpi5_sd_transfer_result rpi5_sd_transfer(struct rpi5_sd_card *card,
    struct rpi5_sd_write_policy *policy, uint64_t epoch, enum rpi5_sd_transfer_kind kind,
    uint64_t block, uint64_t count, const struct rpi5_sd_buffer *buffer, void *scratch, size_t scratch_bytes)
{
    struct rpi5_sd_transfer_result result={.status=RPI5_SD_INVALID};
    if (!card || !buffer || !scratch || !buffer->prepare || !buffer->complete || !buffer->continuing ||
        !card->ready || !rpi5_sd_read_request_valid(card->sectors,block,count,buffer->bytes)) return result;
    if (kind==RPI5_SD_TRANSFER_WRITE) {
        if (!buffer->copy_from || scratch_bytes<buffer->bytes ||
            !rpi5_sd_write_request_valid(policy,epoch,block,count,buffer->bytes)) return result;
    } else if (kind!=RPI5_SD_TRANSFER_READ || !buffer->copy_to || scratch_bytes<512) return result;
    if (!buffer->continuing(buffer->context)) { result.status=RPI5_SD_CANCELLED; return result; }
    result.memory_status=buffer->prepare(buffer->context,kind);
    if (result.memory_status) { result.status=RPI5_SD_BUFFER_ERROR; return result; }
    result.status=RPI5_SD_OK;
    if (kind==RPI5_SD_TRANSFER_WRITE &&
        buffer->copy_from(buffer->context,0,scratch,(size_t)buffer->bytes)!=buffer->bytes)
        result.status=RPI5_SD_BUFFER_ERROR;
    for (uint64_t i=0;!result.status && i<count;i++) {
        if (!buffer->continuing(buffer->context)) { result.status=RPI5_SD_CANCELLED; break; }
        if (!card->ready) { result.status=RPI5_SD_CARD; break; }
        if (kind==RPI5_SD_TRANSFER_WRITE) {
            if (!rpi5_sd_write_request_valid(policy,epoch,block+i,count-i,(count-i)*512)) {
                result.status=RPI5_SD_INVALID; break;
            }
            result.attempted_sectors++;
            result.status=rpi5_sd_write_sector(card,policy,epoch,block+i,(uint8_t *)scratch+i*512,512);
        } else {
            result.attempted_sectors++;
            result.status=rpi5_sd_read_sector(card,block+i,scratch,512);
            if (result.status) {
                card->ready=0;
                rpi5_sd_write_quarantine(policy); /* Reads must not leave a writable lease usable after I/O failure. */
            }
            if (!result.status && buffer->copy_to(buffer->context,i*512,scratch,512)!=512)
                result.status=RPI5_SD_BUFFER_ERROR;
        }
        if (!result.status) result.actual_bytes+=512;
    }
    result.cleanup_status=buffer->complete(buffer->context,kind);
    if (!result.status && result.cleanup_status) result.status=RPI5_SD_CLEANUP_ERROR;
    if (kind==RPI5_SD_TRANSFER_WRITE && result.status && result.attempted_sectors) {
        card->ready=0;
        rpi5_sd_write_quarantine(policy);
    }
    return result;
}
