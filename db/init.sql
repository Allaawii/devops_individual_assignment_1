-- Local only: create the two databases and one login per service. Run by the db-init container
-- in docker-compose.yml with sqlcmd as sa. Safe to run again: everything is "create if missing",
-- and the passwords are reset to the values given, so changing them in .env takes effect.
-- The passwords come in as sqlcmd variables: $(CONTENT_PASSWORD) and $(SCHEDULER_PASSWORD).
-- On Azure the same logins and users are created once by infra/setup.sh instead.

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

-- Each login is a user in its own database only, as db_owner: enough for the migrations to
-- create and change tables, and no access at all to the other service's data.
USE content;
IF USER_ID(N'content_svc') IS NULL CREATE USER content_svc FOR LOGIN content_svc;
ALTER ROLE db_owner ADD MEMBER content_svc;
GO

USE scheduler;
IF USER_ID(N'scheduler_svc') IS NULL CREATE USER scheduler_svc FOR LOGIN scheduler_svc;
ALTER ROLE db_owner ADD MEMBER scheduler_svc;
GO

PRINT 'db-init: databases content and scheduler, logins content_svc and scheduler_svc are ready';
