CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    department VARCHAR(100) NOT NULL,
    role VARCHAR(100) NOT NULL,
    salary INTEGER NOT NULL,
    skills TEXT NOT NULL
);

INSERT INTO employees (name, department, role, salary, skills) VALUES
('Asha Sharma', 'AI', 'ML Engineer', 1800000, 'Python, PyTorch, NLP'),
('Rohan Patil', 'Data', 'Data Scientist', 1600000, 'Python, SQL, Pandas, ML'),
('Neha Kulkarni', 'Platform', 'Backend Engineer', 1500000, 'Python, FastAPI, PostgreSQL'),
('Vikram Joshi', 'AI', 'LLM Engineer', 2100000, 'Python, RAG, LangChain, Vector DB'),
('Sneha Deshmukh', 'Analytics', 'BI Analyst', 1200000, 'SQL, Power BI, DAX');

CREATE TABLE IF NOT EXISTS loan_applications (
    id SERIAL PRIMARY KEY,
    applicant_name VARCHAR(100) NOT NULL,
    monthly_income NUMERIC(12, 2) NOT NULL CHECK (monthly_income > 0),
    monthly_debt NUMERIC(12, 2) NOT NULL CHECK (monthly_debt >= 0),
    requested_payment NUMERIC(12, 2) NOT NULL CHECK (requested_payment > 0),
    employment_months INTEGER NOT NULL CHECK (employment_months >= 0),
    credit_score INTEGER NOT NULL CHECK (credit_score BETWEEN 300 AND 850),
    loan_amount NUMERIC(12, 2) NOT NULL DEFAULT 30000 CHECK (loan_amount > 0),
    term_months INTEGER NOT NULL DEFAULT 36 CHECK (term_months > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO loan_applications (
    applicant_name, monthly_income, monthly_debt, requested_payment,
    employment_months, credit_score, loan_amount, term_months
) VALUES
('Maya Rao', 90000, 18000, 22000, 48, 760, 30000, 36),
('Arjun Mehta', 55000, 24000, 19000, 14, 670, 25000, 36),
('Kiran Das', 42000, 26000, 18000, 5, 595, 18000, 24);

CREATE TABLE IF NOT EXISTS application_documents (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES loan_applications(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    document_type VARCHAR(80) NOT NULL,
    extracted_status VARCHAR(40) NOT NULL DEFAULT 'queued',
    extracted_income NUMERIC(12, 2),
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_events (
    id SERIAL PRIMARY KEY,
    application_id INTEGER REFERENCES loan_applications(id) ON DELETE CASCADE,
    event_type VARCHAR(80) NOT NULL,
    reviewer VARCHAR(100) NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS repayment_events (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES loan_applications(id) ON DELETE CASCADE,
    due_date DATE NOT NULL,
    amount_due NUMERIC(12, 2) NOT NULL CHECK (amount_due > 0),
    amount_paid NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (amount_paid >= 0),
    paid_at TIMESTAMPTZ
);

INSERT INTO repayment_events (application_id, due_date, amount_due, amount_paid, paid_at) VALUES
(1, CURRENT_DATE - INTERVAL '30 days', 22000, 22000, NOW() - INTERVAL '25 days'),
(1, CURRENT_DATE, 22000, 0, NULL),
(2, CURRENT_DATE - INTERVAL '30 days', 19000, 14000, NOW() - INTERVAL '22 days'),
(3, CURRENT_DATE - INTERVAL '30 days', 18000, 0, NULL);
