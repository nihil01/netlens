-- Missing FMC event time is unknown, not the NetLens collection timestamp.
ALTER TABLE fmc_audit_records ALTER COLUMN timestamp DROP NOT NULL;
