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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO loan_applications (
    applicant_name, monthly_income, monthly_debt, requested_payment,
    employment_months, credit_score
) VALUES
('Maya Rao', 90000, 18000, 22000, 48, 760),
('Arjun Mehta', 55000, 24000, 19000, 14, 670),
('Kiran Das', 42000, 26000, 18000, 5, 595);
