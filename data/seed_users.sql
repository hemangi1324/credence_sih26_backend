BEGIN;

INSERT INTO users (user_id, name, role, department_id) VALUES 
('u1', 'S. Deshmukh', 'SECTION_CONTROLLER', NULL),
('u2', 'A. Bhosale', 'BDMS_INCHARGE', 1),
('u3', 'V. Kumar', 'FIELD_MANAGER', 2),
('u4', 'R. Sharma', 'BDMS_INCHARGE', 2),
('u5', 'K. Iyer', 'BDMS_INCHARGE', 3),
('u6', 'M. Patil', 'FIELD_MANAGER', 1)
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO user_sections (user_id, section_id) VALUES
('u1', 3),
('u1', 4),
('u1', 5),
('u2', 3),
('u3', 3),
('u4', 5),
('u5', 4),
('u6', 3)
ON CONFLICT DO NOTHING;

COMMIT;
