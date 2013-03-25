CREATE TABLE misc(
        id SERIAL PRIMARY KEY,
        item VARCHAR(32) NOT NULL,
        val VARCHAR(32) DEFAULT '',
        detail TEXT DEFAULT ''
);

CREATE TABLE request_queue(
    id SERIAL PRIMARY KEY,
    cdate TIMESTAMP DEFAULT current_timestamp,
    ldate TIMESTAMP DEFAULT current_timestamp,
    msisdn VARCHAR(32) NOT NULL DEFAULT '',
    req_path TEXT NOT NULL,
    req_body TEXT DEFAULT '',
    sesid TEXT DEFAULT '',
    status VARCHAR(32) DEFAULT 'ready',
    statuscode TEXT,
    remote_addr TEXT NOT NULL DEFAULT '',
);

CREATE TABLE thirdparty_users(
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL DEFAULT '',
    password TEXT NOT NULL,
    failed_attempts VARCHAR(16) DEFAULT '0/'||to_char(now(),'yyyymmdd'),
    transaction_limit TEXT DEFAULT '0/'||to_char(now(),'yyyymmdd'),
    is_active BOOLEAN DEFAULT TRUE,
    ip_mask TEXT NOT NULL DEFAULT '::1,127.0.0.1',
    cdate TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE audit_logs(
        id BIGSERIAL PRIMARY KEY,
        remote_ip INET,
        audit_identity INTEGER REFERENCES thirdparty_users(id),
        action TEXT NOT NULL DEFAULT '',
        detail TEXT NOT NULL DEFAULT '',
        cdate TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE INDEX audit_logs_action_idx ON audit_logs(action);

CREATE TABLE message_log(
        id BIGSERIAL PRIMARY KEY,
        userid INTEGER REFERENCES thirdparty_users(id),
        text TEXT NOT NULL DEFAULT '',
        recipient_count INTEGER NOT NULL,
        recipient TEXT NOT NULL DEFAULT '',
        backend TEXT NOT NULL DEFAULT '',
        cdate TIMESTAMP NOT NULL DEFAULT current_timestamp
);

INSERT INTO thirdparty_users(username,password,is_active,ip_mask)
	VALUES('dhis',crypt('dHiStwo',gen_salt('bf')), 't','::1,127.0.0.1');
