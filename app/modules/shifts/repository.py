import json


def latest(db, run_id, shift):
    return db.execute('SELECT * FROM shift_runs WHERE run_id=? AND shift=? '
                      'ORDER BY version DESC LIMIT 1', (run_id, shift)).fetchone()


def by_id(db, adjudication_id):
    return db.execute('SELECT * FROM shift_runs WHERE id=?', (adjudication_id,)).fetchone()


def versions(db, run_id, shift):
    return [dict(row) for row in db.execute(
        'SELECT version,strategy,created,id FROM shift_runs WHERE run_id=? AND shift=? '
        'ORDER BY version DESC', (run_id, shift))]


def save(db, adjudication_id, run_id, shift, version, strategy, picked, payload, created):
    db.execute('INSERT INTO shift_runs VALUES (?,?,?,?,?,?,?,?)',
               (adjudication_id, run_id, shift, version, strategy,
                json.dumps(picked, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False), created))


def reviews(db, run_id, shift):
    return [dict(row) for row in db.execute(
        'SELECT version,adjudication,decision,note,changed FROM shift_reviews '
        'WHERE run_id=? AND shift=? ORDER BY version DESC', (run_id, shift))]


def save_review(db, run_id, shift, version, adjudication, decision, note, changed):
    db.execute('INSERT INTO shift_reviews VALUES (?,?,?,?,?,?,?)',
               (run_id, shift, version, adjudication, decision, note, changed))
