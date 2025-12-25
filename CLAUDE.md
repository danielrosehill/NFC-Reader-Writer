# NFC-GUI Project Instructions

## Overview
NFC Reader/Writer GUI application for ACS ACR1252U USB NFC Reader. Supports reading, writing, and updating NTAG213/215/216 tags.

## TTS Voice Announcements

### Generation Method
TTS audio files are generated using **edge-tts** with a British English voice and saved in the repo.

**Voice**: `en-GB-RyanNeural` (British male)

**Output format**: OGG (converted from MP3)

### Generate TTS Files
```bash
# Generate a single TTS file
edge-tts --voice en-GB-RyanNeural --text "Your message here" --write-media /tmp/output.mp3
ffmpeg -i /tmp/output.mp3 -c:a libvorbis -q:a 5 nfc_gui/sounds/filename.ogg

# Or in one line:
edge-tts --voice en-GB-RyanNeural --text "Message" --write-media /tmp/tts.mp3 && ffmpeg -y -i /tmp/tts.mp3 -c:a libvorbis -q:a 5 nfc_gui/sounds/filename.ogg
```

### Sound Files Location
All TTS files are stored in: `nfc_gui/sounds/`

### Existing TTS Announcements
- `tag_opened.ogg` - "Tag opened"
- `tag_written.ogg` - "Tag written and locked"
- `tag_updated.ogg` - "Tag updated"
- `tag_up_to_date.ogg` - "Tag already up to date"
- `tag_has_data.ogg` - "Tag has existing data"
- `tag_locked.ogg` - "Tag is locked"
- `batch_started.ogg` - "Batch started"
- `batch_finished.ogg` - "Batch finished"
- `read_mode.ogg` - "Read mode"
- `ready_to_write.ogg` - "Ready to write"
- `update_mode.ogg` - "Update mode"
- `update_failed.ogg` - "Update failed"
- `write_failed.ogg` - "Write failed"
- `read_failed.ogg` - "Read failed"
- `comm_error.ogg` - "Communication error"
- `no_reader.ogg` - "No reader found"
- `no_tag_found.ogg` - "No tag found"
- `background_mode.ogg` - "Background mode active"
- `closing.ogg` - "Goodbye"
- `url_validated.ogg` - "URL validated"
- `url_updated.ogg` - "URL updated"
- `present_tag.ogg` - "Present tag"
- `outdated_tag_detected.ogg` - "Outdated tag detected"

## Update Mode Workflow

Update mode is a **two-step workflow**:

1. **Step 1 (Scan old tag)**: User presents a tag with the old URL pattern
   - App reads URL, checks if it matches the configured source pattern
   - If outdated: stores rewritten URL, announces "Outdated tag detected", prompts for new tag

2. **Step 2 (Write new tag)**: User presents a new blank tag
   - App writes the rewritten URL to the new tag
   - Locks the tag permanently
   - Resets to Step 1 for next update

## Development Notes

- PyQt5 GUI application
- pyscard for NFC communication
- Settings stored in `~/.config/nfc-reader/config.json`
- Sound files played via `paplay` (PulseAudio/PipeWire)
