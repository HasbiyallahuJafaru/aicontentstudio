-- 2026-11-08: Buffer and Metricool were removed (owner decision); Zernio is the only posting service. Their saved
-- connections and the media-host keys they needed are deleted. Old publications rows stay as history.
DELETE FROM credentials WHERE name IN ('buffer', 'metricool', 'metricool_client', 'publish_host') OR name LIKE 'oauth:%';
