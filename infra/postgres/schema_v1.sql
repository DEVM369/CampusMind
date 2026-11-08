-- CampusMind baseline schema v1

CREATE EXTENSION IF NOT EXISTS vector;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE colleges (
	code VARCHAR(32) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE UNIQUE INDEX ix_colleges_code ON colleges (code);

CREATE TABLE evaluation_datasets (
	name VARCHAR(128) NOT NULL, 
	version VARCHAR(64) NOT NULL, 
	description TEXT, 
	status VARCHAR(32) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_evaluation_datasets_name ON evaluation_datasets (name);

CREATE INDEX ix_evaluation_datasets_status ON evaluation_datasets (status);

CREATE INDEX ix_evaluation_datasets_version ON evaluation_datasets (version);

CREATE TABLE knowledge_bases (
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	domain VARCHAR(32) NOT NULL, 
	description TEXT, 
	visibility VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_knowledge_bases_code ON knowledge_bases (code);

CREATE INDEX ix_knowledge_bases_domain ON knowledge_bases (domain);

CREATE INDEX ix_knowledge_bases_status ON knowledge_bases (status);

CREATE TABLE permissions (
	code VARCHAR(128) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	description TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_permissions_code ON permissions (code);

CREATE TABLE roles (
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	description TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_roles_code ON roles (code);

CREATE TABLE users (
	username VARCHAR(64) NOT NULL, 
	email VARCHAR(255), 
	password_hash VARCHAR(255), 
	full_name VARCHAR(128) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	is_superuser BOOLEAN NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE INDEX ix_users_status ON users (status);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE TABLE audit_logs (
	actor_user_id UUID, 
	action VARCHAR(128) NOT NULL, 
	resource_type VARCHAR(64) NOT NULL, 
	resource_id VARCHAR(128), 
	request_id VARCHAR(128), 
	ip_address VARCHAR(64), 
	detail_json JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_logs_action ON audit_logs (action);

CREATE INDEX ix_audit_logs_actor_user_id ON audit_logs (actor_user_id);

CREATE INDEX ix_audit_logs_request_id ON audit_logs (request_id);

CREATE INDEX ix_audit_logs_resource_id ON audit_logs (resource_id);

CREATE INDEX ix_audit_logs_resource_type ON audit_logs (resource_type);

CREATE TABLE conversations (
	user_id UUID NOT NULL, 
	title VARCHAR(255), 
	status VARCHAR(32) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_conversations_status ON conversations (status);

CREATE INDEX ix_conversations_user_id ON conversations (user_id);

CREATE TABLE departments (
	college_id UUID NOT NULL, 
	code VARCHAR(32) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(college_id) REFERENCES colleges (id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX ix_departments_code ON departments (code);

CREATE INDEX ix_departments_college_id ON departments (college_id);

CREATE TABLE documents (
	knowledge_base_id UUID NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	object_key VARCHAR(512) NOT NULL, 
	mime_type VARCHAR(128) NOT NULL, 
	checksum_sha256 VARCHAR(64), 
	document_type VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_bases (id) ON DELETE CASCADE, 
	UNIQUE (object_key)
);

CREATE INDEX ix_documents_checksum_sha256 ON documents (checksum_sha256);

CREATE INDEX ix_documents_document_type ON documents (document_type);

CREATE INDEX ix_documents_knowledge_base_id ON documents (knowledge_base_id);

CREATE INDEX ix_documents_status ON documents (status);

CREATE INDEX ix_documents_title ON documents (title);

CREATE TABLE evaluation_cases (
	dataset_id UUID NOT NULL, 
	category VARCHAR(64) NOT NULL, 
	question TEXT NOT NULL, 
	expected_answer TEXT, 
	expected_evidence JSON NOT NULL, 
	metadata_json JSON NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(dataset_id) REFERENCES evaluation_datasets (id) ON DELETE CASCADE
);

CREATE INDEX ix_evaluation_cases_category ON evaluation_cases (category);

CREATE INDEX ix_evaluation_cases_dataset_id ON evaluation_cases (dataset_id);

CREATE TABLE role_permissions (
	role_id UUID NOT NULL, 
	permission_id UUID NOT NULL, 
	PRIMARY KEY (role_id, permission_id), 
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
	FOREIGN KEY(permission_id) REFERENCES permissions (id) ON DELETE CASCADE
);

CREATE TABLE user_roles (
	user_id UUID NOT NULL, 
	role_id UUID NOT NULL, 
	PRIMARY KEY (user_id, role_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE
);

CREATE TABLE agent_runs (
	user_id UUID, 
	conversation_id UUID, 
	query TEXT NOT NULL, 
	intent VARCHAR(64), 
	complexity VARCHAR(32), 
	risk_level VARCHAR(32) NOT NULL, 
	retrieval_strategy VARCHAR(64), 
	status VARCHAR(32) NOT NULL, 
	validation_score NUMERIC(5, 4), 
	final_answer TEXT, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	latency_ms INTEGER, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE SET NULL
);

CREATE INDEX ix_agent_runs_complexity ON agent_runs (complexity);

CREATE INDEX ix_agent_runs_conversation_id ON agent_runs (conversation_id);

CREATE INDEX ix_agent_runs_intent ON agent_runs (intent);

CREATE INDEX ix_agent_runs_retrieval_strategy ON agent_runs (retrieval_strategy);

CREATE INDEX ix_agent_runs_risk_level ON agent_runs (risk_level);

CREATE INDEX ix_agent_runs_status ON agent_runs (status);

CREATE INDEX ix_agent_runs_user_id ON agent_runs (user_id);

CREATE TABLE courses (
	department_id UUID NOT NULL, 
	code VARCHAR(32) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	credits NUMERIC(4, 1) NOT NULL, 
	course_type VARCHAR(32) NOT NULL, 
	description TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX ix_courses_code ON courses (code);

CREATE INDEX ix_courses_department_id ON courses (department_id);

CREATE INDEX ix_courses_name ON courses (name);

CREATE TABLE document_permissions (
	document_id UUID NOT NULL, 
	subject_type VARCHAR(16) NOT NULL, 
	subject_id UUID NOT NULL, 
	permission_level VARCHAR(32) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_document_permission_subject UNIQUE (document_id, subject_type, subject_id), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);

CREATE INDEX ix_document_permissions_document_id ON document_permissions (document_id);

CREATE INDEX ix_document_permissions_subject_id ON document_permissions (subject_id);

CREATE INDEX ix_document_permissions_subject_type ON document_permissions (subject_type);

CREATE TABLE document_versions (
	document_id UUID NOT NULL, 
	version VARCHAR(64) NOT NULL, 
	object_key VARCHAR(512) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	effective_from DATE, 
	effective_to DATE, 
	published_at TIMESTAMP WITH TIME ZONE, 
	department VARCHAR(128), 
	metadata_json JSON NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_document_version UNIQUE (document_id, version), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);

CREATE INDEX ix_document_versions_department ON document_versions (department);

CREATE INDEX ix_document_versions_document_id ON document_versions (document_id);

CREATE INDEX ix_document_versions_effective_from ON document_versions (effective_from);

CREATE INDEX ix_document_versions_effective_to ON document_versions (effective_to);

CREATE INDEX ix_document_versions_status ON document_versions (status);

CREATE TABLE majors (
	college_id UUID NOT NULL, 
	department_id UUID, 
	code VARCHAR(32) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	degree_type VARCHAR(32) NOT NULL, 
	graduation_credits INTEGER NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(college_id) REFERENCES colleges (id) ON DELETE RESTRICT, 
	FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX ix_majors_code ON majors (code);

CREATE INDEX ix_majors_college_id ON majors (college_id);

CREATE INDEX ix_majors_department_id ON majors (department_id);

CREATE TABLE messages (
	conversation_id UUID NOT NULL, 
	role VARCHAR(32) NOT NULL, 
	content TEXT NOT NULL, 
	citations JSON NOT NULL, 
	metadata_json JSON NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
);

CREATE INDEX ix_messages_conversation_id ON messages (conversation_id);

CREATE INDEX ix_messages_role ON messages (role);

CREATE TABLE teachers (
	user_id UUID NOT NULL, 
	employee_no VARCHAR(32) NOT NULL, 
	department_id UUID NOT NULL, 
	title VARCHAR(64), 
	bio TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE RESTRICT
);

CREATE INDEX ix_teachers_department_id ON teachers (department_id);

CREATE UNIQUE INDEX ix_teachers_employee_no ON teachers (employee_no);

CREATE UNIQUE INDEX ix_teachers_user_id ON teachers (user_id);

CREATE TABLE agent_steps (
	agent_run_id UUID NOT NULL, 
	sequence_no INTEGER NOT NULL, 
	step_name VARCHAR(128) NOT NULL, 
	step_type VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	input_json JSON NOT NULL, 
	output_json JSON NOT NULL, 
	latency_ms INTEGER, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(agent_run_id) REFERENCES agent_runs (id) ON DELETE CASCADE
);

CREATE INDEX ix_agent_steps_agent_run_id ON agent_steps (agent_run_id);

CREATE INDEX ix_agent_steps_status ON agent_steps (status);

CREATE INDEX ix_agent_steps_step_name ON agent_steps (step_name);

CREATE INDEX ix_agent_steps_step_type ON agent_steps (step_type);

CREATE TABLE course_prerequisites (
	course_id UUID NOT NULL, 
	prerequisite_course_id UUID NOT NULL, 
	relation_type VARCHAR(32) NOT NULL, 
	PRIMARY KEY (course_id, prerequisite_course_id), 
	CONSTRAINT uq_course_prerequisite UNIQUE (course_id, prerequisite_course_id), 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE CASCADE, 
	FOREIGN KEY(prerequisite_course_id) REFERENCES courses (id) ON DELETE CASCADE
);

CREATE TABLE document_chunks (
	document_id UUID NOT NULL, 
	document_version_id UUID NOT NULL, 
	knowledge_base_id UUID NOT NULL, 
	chunk_index INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	token_count INTEGER, 
	page INTEGER, 
	chapter VARCHAR(255), 
	section VARCHAR(255), 
	department VARCHAR(128), 
	document_type VARCHAR(64), 
	effective_date DATE, 
	permission_level VARCHAR(32) NOT NULL, 
	metadata_json JSON NOT NULL, 
	embedding vector, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_document_chunk_index UNIQUE (document_version_id, chunk_index), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
	FOREIGN KEY(document_version_id) REFERENCES document_versions (id) ON DELETE CASCADE, 
	FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_bases (id) ON DELETE CASCADE
);

CREATE INDEX ix_document_chunks_department ON document_chunks (department);

CREATE INDEX ix_document_chunks_document_id ON document_chunks (document_id);

CREATE INDEX ix_document_chunks_document_type ON document_chunks (document_type);

CREATE INDEX ix_document_chunks_document_version_id ON document_chunks (document_version_id);

CREATE INDEX ix_document_chunks_effective_date ON document_chunks (effective_date);

CREATE INDEX ix_document_chunks_knowledge_base_id ON document_chunks (knowledge_base_id);

CREATE INDEX ix_document_chunks_page ON document_chunks (page);

CREATE INDEX ix_document_chunks_permission_level ON document_chunks (permission_level);

CREATE INDEX ix_document_chunks_section ON document_chunks (section);

CREATE TABLE evaluation_results (
	dataset_id UUID NOT NULL, 
	case_id UUID, 
	agent_run_id UUID, 
	score NUMERIC(6, 4), 
	passed BOOLEAN, 
	metrics_json JSON NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(dataset_id) REFERENCES evaluation_datasets (id) ON DELETE CASCADE, 
	FOREIGN KEY(case_id) REFERENCES evaluation_cases (id) ON DELETE CASCADE, 
	FOREIGN KEY(agent_run_id) REFERENCES agent_runs (id) ON DELETE SET NULL
);

CREATE INDEX ix_evaluation_results_agent_run_id ON evaluation_results (agent_run_id);

CREATE INDEX ix_evaluation_results_case_id ON evaluation_results (case_id);

CREATE INDEX ix_evaluation_results_dataset_id ON evaluation_results (dataset_id);

CREATE TABLE students (
	user_id UUID NOT NULL, 
	student_no VARCHAR(32) NOT NULL, 
	major_id UUID NOT NULL, 
	enrollment_year INTEGER NOT NULL, 
	grade_level INTEGER NOT NULL, 
	total_credits NUMERIC(6, 2) NOT NULL, 
	expected_graduation_date DATE, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(major_id) REFERENCES majors (id) ON DELETE RESTRICT
);

CREATE INDEX ix_students_major_id ON students (major_id);

CREATE UNIQUE INDEX ix_students_student_no ON students (student_no);

CREATE UNIQUE INDEX ix_students_user_id ON students (user_id);

CREATE TABLE teaching_assignments (
	teacher_id UUID NOT NULL, 
	course_id UUID NOT NULL, 
	semester VARCHAR(32) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_teacher_course_semester UNIQUE (teacher_id, course_id, semester), 
	FOREIGN KEY(teacher_id) REFERENCES teachers (id) ON DELETE CASCADE, 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE CASCADE
);

CREATE INDEX ix_teaching_assignments_course_id ON teaching_assignments (course_id);

CREATE INDEX ix_teaching_assignments_semester ON teaching_assignments (semester);

CREATE INDEX ix_teaching_assignments_teacher_id ON teaching_assignments (teacher_id);

CREATE TABLE student_courses (
	student_id UUID NOT NULL, 
	course_id UUID NOT NULL, 
	semester VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	score NUMERIC(5, 2), 
	credits_earned NUMERIC(4, 1) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_student_course_semester UNIQUE (student_id, course_id, semester), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE RESTRICT
);

CREATE INDEX ix_student_courses_course_id ON student_courses (course_id);

CREATE INDEX ix_student_courses_semester ON student_courses (semester);

CREATE INDEX ix_student_courses_student_id ON student_courses (student_id);

CREATE TABLE tool_calls (
	agent_run_id UUID NOT NULL, 
	agent_step_id UUID, 
	tool_name VARCHAR(128) NOT NULL, 
	arguments_json JSON NOT NULL, 
	result_json JSON NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	requires_approval BOOLEAN NOT NULL, 
	approved_by_user_id UUID, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(agent_run_id) REFERENCES agent_runs (id) ON DELETE CASCADE, 
	FOREIGN KEY(agent_step_id) REFERENCES agent_steps (id) ON DELETE SET NULL, 
	FOREIGN KEY(approved_by_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_tool_calls_agent_run_id ON tool_calls (agent_run_id);

CREATE INDEX ix_tool_calls_agent_step_id ON tool_calls (agent_step_id);

CREATE INDEX ix_tool_calls_status ON tool_calls (status);

CREATE INDEX ix_tool_calls_tool_name ON tool_calls (tool_name);
