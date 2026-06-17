-- Backup of production database

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL
);

INSERT INTO users (username, email, password_hash) VALUES
('johndoe', 'john@example.com', '$2b$12$abcdefg...'),
('janedoe', 'jane@example.com', '$2b$12$hijklmn...');

CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    amount DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO transactions (user_id, amount) VALUES
(1, 250.00),
(2, 420.50);
