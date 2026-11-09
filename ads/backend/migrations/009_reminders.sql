-- Reminders about leads nobody has contacted (5 min to the owner, 1 h to admins, 8 AM list).
ALTER TABLE users ADD COLUMN notify_reminders BOOLEAN NOT NULL DEFAULT TRUE;
