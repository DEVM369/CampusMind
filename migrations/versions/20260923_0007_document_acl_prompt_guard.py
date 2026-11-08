"""CampusMind document ACL RLS and prompt-injection quarantine.

Revision ID: 20260923_0007
Revises: 20260923_0006
"""

from alembic import op


revision = "20260923_0007"
down_revision = "20260923_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Custom GUC values are transaction-local and are set by KnowledgeAclService.
    # When no document security layer context exists (legacy internal verification/maintenance),
    # preserve the historical public+campus corpus behavior.
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION campusmind_acl_levels()
        RETURNS text[]
        LANGUAGE sql
        STABLE
        AS $$
            SELECT CASE
                WHEN COALESCE(current_setting('campusmind.permission_levels', true), '') = ''
                    THEN ARRAY['public', 'campus']::text[]
                ELSE regexp_split_to_array(
                    lower(current_setting('campusmind.permission_levels', true)),
                    '\s*,\s*'
                )
            END
        $$
        """
    )

    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION campusmind_normalize_permission_level(value text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE
        AS $$
            SELECT CASE lower(COALESCE(value, 'public'))
                WHEN '公开' THEN 'public'
                WHEN '校内' THEN 'campus'
                WHEN '学生' THEN 'student'
                WHEN '教师' THEN 'teacher'
                WHEN '行政' THEN 'staff'
                WHEN '院系' THEN 'department'
                WHEN '个人' THEN 'personal'
                WHEN '管理员' THEN 'admin'
                ELSE lower(COALESCE(value, 'public'))
            END
        $$
        """
    )

    # Deliberately narrow/high-signal detector. Suspicious chunks remain stored
    # for audit/admin review, but are quarantined from retrieval until an
    # explicit metadata_json.security_reviewed=true marker is applied.
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION campusmind_prompt_injection_suspect(value text)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        AS $$
            SELECT COALESCE(value, '') ~* (
                '(ignore|disregard|forget)[[:space:]]+(all[[:space:]]+)?' ||
                '(previous|prior|system|developer)[[:space:]]+' ||
                '(instructions?|messages?|prompts?)' ||
                '|system[[:space:]]*prompt' ||
                '|developer[[:space:]]*message' ||
                '|(reveal|print|return|exfiltrat[^[:space:]]*).{0,60}' ||
                '(password|secret|api[[:space:]]*key|database|system[[:space:]]*prompt)' ||
                '|(call|invoke|execute|run).{0,40}(tool|command|shell|sql)' ||
                '|忽略.{0,16}(系统|之前|以上|开发者).{0,16}(指令|提示|规则)' ||
                '|(泄露|返回|输出|展示).{0,24}(数据库|密码|密钥|系统提示|开发者消息)' ||
                '|(执行|调用|运行).{0,16}(工具|命令|Shell|SQL)'
            )
        $$
        """
    )

    op.execute("ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS campusmind_document_chunks_acl ON document_chunks")

    op.execute(
        r"""
        CREATE POLICY campusmind_document_chunks_acl
        ON document_chunks
        FOR ALL
        USING (
            '*' = ANY(campusmind_acl_levels())
            OR (
                campusmind_normalize_permission_level(permission_level)
                    = ANY(campusmind_acl_levels())
                AND (
                    campusmind_normalize_permission_level(permission_level) <> 'personal'
                    OR COALESCE(
                        metadata_json ->> 'owner_user_id',
                        metadata_json ->> 'actor_user_id',
                        ''
                    ) = COALESCE(current_setting('campusmind.actor_user_id', true), '')
                )
                AND (
                    NOT campusmind_prompt_injection_suspect(content)
                    OR lower(COALESCE(metadata_json ->> 'security_reviewed', 'false'))
                        IN ('true', '1', 'yes')
                )
            )
        )
        WITH CHECK (
            '*' = ANY(campusmind_acl_levels())
            OR (
                campusmind_normalize_permission_level(permission_level)
                    = ANY(campusmind_acl_levels())
                AND (
                    campusmind_normalize_permission_level(permission_level) <> 'personal'
                    OR COALESCE(
                        metadata_json ->> 'owner_user_id',
                        metadata_json ->> 'actor_user_id',
                        ''
                    ) = COALESCE(current_setting('campusmind.actor_user_id', true), '')
                )
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS campusmind_document_chunks_acl ON document_chunks")
    op.execute("ALTER TABLE document_chunks NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_chunks DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS campusmind_prompt_injection_suspect(text)")
    op.execute("DROP FUNCTION IF EXISTS campusmind_normalize_permission_level(text)")
    op.execute("DROP FUNCTION IF EXISTS campusmind_acl_levels()")
