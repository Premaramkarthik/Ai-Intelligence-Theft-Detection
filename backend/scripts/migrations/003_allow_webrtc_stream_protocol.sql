ALTER TABLE stream_state
DROP CONSTRAINT IF EXISTS stream_state_protocol_check;

ALTER TABLE stream_state
ADD CONSTRAINT stream_state_protocol_check
CHECK (protocol IN ('webrtc', 'hls'));

ALTER TABLE stream_state
ALTER COLUMN protocol SET DEFAULT 'webrtc';
