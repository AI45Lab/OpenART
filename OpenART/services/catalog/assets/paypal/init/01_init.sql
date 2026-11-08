CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Core tables
CREATE TABLE IF NOT EXISTS products(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS disputes(
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  details JSONB
);

CREATE TABLE IF NOT EXISTS invoices(
  id TEXT PRIMARY KEY,
  recipient_email TEXT NOT NULL,
  status TEXT NOT NULL,
  items JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS orders(
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  currency TEXT NOT NULL,
  items JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS refunds(
  id TEXT PRIMARY KEY,
  capture_id TEXT NOT NULL,
  amount DOUBLE PRECISION,
  currency TEXT
);

CREATE TABLE IF NOT EXISTS transactions(
  id TEXT PRIMARY KEY,
  date DATE NOT NULL,
  details JSONB
);

CREATE TABLE IF NOT EXISTS shipments(
  transaction_id TEXT NOT NULL,
  tracking_number TEXT NOT NULL,
  carrier TEXT,
  order_id TEXT,
  status TEXT,
  PRIMARY KEY (transaction_id, tracking_number)
);

CREATE TABLE IF NOT EXISTS subscriptions(
  id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL,
  subscriber_name TEXT,
  subscriber_email TEXT,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subscription_plans(
  id TEXT PRIMARY KEY,
  product_id TEXT NOT NULL,
  name TEXT NOT NULL,
  billing_cycles JSONB NOT NULL,
  payment_preferences JSONB NOT NULL,
  auto_bill_outstanding BOOLEAN
);

CREATE TABLE IF NOT EXISTS carts(
  id TEXT PRIMARY KEY,
  items JSONB NOT NULL,
  shipping_prefs JSONB
);

-- No default seed rows: products/transactions/etc. start empty. Business data
-- is created by the agent during a task; tenant-agnostic default rows would
-- otherwise leak into the next task (and reset wipes them anyway).


