CREATE TABLE sensor_data (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  temperatura float,
  presion     float,
  altitud     float,
  humedad     float,
  created_at  timestamptz DEFAULT now()
);

ALTER TABLE sensor_data ENABLE ROW LEVEL SECURITY;

CREATE POLICY "solo lectura publica"
  ON sensor_data FOR SELECT USING (true);

CREATE POLICY "escritura service role"
  ON sensor_data FOR INSERT
  TO service_role WITH CHECK (true);
