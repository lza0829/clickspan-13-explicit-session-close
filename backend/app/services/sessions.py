from app.modules import explicit_session_close as esc


def list_sessions(conn, visitor_id: str | None = None):
    if visitor_id:
        rows = conn.execute(
            """
            SELECT id, visitor_id, started_at, ended_at, hit_count, status
            FROM sessions WHERE visitor_id=?
            ORDER BY started_at
            """,
            (visitor_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, visitor_id, started_at, ended_at, hit_count, status
            FROM sessions ORDER BY started_at
            """
        ).fetchall()
    return [dict(r) for r in rows]


def session_detail(conn, session_id: str):
    sess = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not sess:
        return None
    hits = conn.execute(
        """
        SELECT id, visitor_id, session_id, event_ts, page_path, event_name, channel
        FROM hits WHERE session_id=? AND channel='primary'
        ORDER BY event_ts, id
        """,
        (session_id,),
    ).fetchall()
    proof = conn.execute(
        "SELECT * FROM session_proofs WHERE session_id=? ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    # 织机协同：closed 会话须带关闭登记，前端按登记渲染只读快照
    closing = esc.get_closing(conn, session_id)
    return {
        "session": dict(sess),
        "hits": [dict(h) for h in hits],
        "proof": dict(proof) if proof else None,
        "closing": closing,
    }


def close_open_session(conn, session_id: str) -> dict:
    """关闭入口：单事务写登记 + 改状态 + 核证（失败闭路径）。

    BEGIN IMMEDIATE 拿写锁，关闭逻辑全部在同一事务内；任何失败回滚，
    会话保持 open 且不会产生半成品登记。
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        result = esc.close_session(conn, session_id)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
