-- Local only: create the two databases and one login per service. Run by the db-init container
-- in docker-compose.yml with sqlcmd as sa. Safe to run again: everything is "create if missing",
-- and the passwords are reset to the values given, so changing them in .env takes effect.
-- The passwords come in as sqlcmd variables: $(CONTENT_PASSWORD) and $(SCHEDULER_PASSWORD).
-- On Azure, infra/setup.sh creates contained users (no server login) with the same rights instead.

IF DB_ID(N'content') IS NULL CREATE DATABASE content;
IF DB_ID(N'scheduler') IS NULL CREATE DATABASE scheduler;
GO

-- Logins live in the server (master); each service gets its own.
IF SUSER_ID(N'content_svc') IS NULL
    CREATE LOGIN content_svc WITH PASSWORD = N'$(CONTENT_PASSWORD)';
ELSE
    ALTER LOGIN content_svc WITH PASSWORD = N'$(CONTENT_PASSWORD)';

IF SUSER_ID(N'scheduler_svc') IS NULL
    CREATE LOGIN scheduler_svc WITH PASSWORD = N'$(SCHEDULER_PASSWORD)';
ELSE
    ALTER LOGIN scheduler_svc WITH PASSWORD = N'$(SCHEDULER_PASSWORD)';
GO

-- Each login is a user in its own database only, with the same rights as on Azure: create and
-- change tables (db_ddladmin), read and write rows, and reference tables in foreign keys. It has
-- no access at all to the other service's database.
USE content;
IF USER_ID(N'content_svc') IS NULL CREATE USER content_svc FOR LOGIN content_svc;
ALTER ROLE db_ddladmin ADD MEMBER content_svc;
ALTER ROLE db_datareader ADD MEMBER content_svc;
ALTER ROLE db_datawriter ADD MEMBER content_svc;
GRANT REFERENCES ON SCHEMA::dbo TO content_svc;
GO

USE scheduler;
IF USER_ID(N'scheduler_svc') IS NULL CREATE USER scheduler_svc FOR LOGIN scheduler_svc;
ALTER ROLE db_ddladmin ADD MEMBER scheduler_svc;
ALTER ROLE db_datareader ADD MEMBER scheduler_svc;
ALTER ROLE db_datawriter ADD MEMBER scheduler_svc;
GRANT REFERENCES ON SCHEMA::dbo TO scheduler_svc;
GO

PRINT 'db-init: databases content and scheduler, logins content_svc and scheduler_svc are ready';
