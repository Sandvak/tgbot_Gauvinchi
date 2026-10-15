import os
import tempfile
from database import Database

def main():
    tmp_dir = tempfile.mkdtemp(prefix="smoke_")
    db_path = os.path.join(tmp_dir, "smoke.sqlite3")
    db = Database(db_path)
    try:
        # ... здесь весь код с тестами (тот, что был внутри with)
        # ...
        print("V2.1 smoke test: OK")
    finally:
        # Убираем временный файл после теста
        try:
            os.remove(db_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass

        db.upsert_telegram_user(1, "alice")
        db.upsert_telegram_user(2, "bob")
        db.upsert_telegram_user(3, "carol")

        db.save_profile(1, {
            "username": "alice", "name": "Alice", "gender": "female",
            "age": 20, "faculty": "IT", "dormitory": "1",
            "description": "Привет", "photo_1": "p1"
        })
        db.save_profile(2, {
            "username": "bob", "name": "Bob", "gender": "male",
            "age": 21, "faculty": "Math", "dormitory": "2",
            "description": "Hello", "photo_1": "p2"
        })
        db.save_profile(3, {
            "username": "carol", "name": "Carol", "gender": "female",
            "age": 22, "faculty": "Design", "dormitory": "7",
            "description": "Hi", "photo_1": "p3"
        })

        u1, u2, u3 = db.get_user(1), db.get_user(2), db.get_user(3)
        assert db.stats()["completed"] == 3

        # Входящий лайк без ответного лайка попадает в очередь.
        assert db.add_like(u2["id"], u1["id"]) is False
        assert db.incoming_likes_count(u1["id"], "male") == 1
        assert db.incoming_likes_count(u1["id"], "female") == 0

        # Ответный лайк превращает симпатию во взаимную и убирает её из очереди.
        assert db.add_like(u1["id"], u2["id"]) is True
        assert db.incoming_likes_count(u1["id"], "male") == 0

        # Жалоба сохраняется, а профиль становится менее приоритетным, но не скрывается сразу.
        report_id, created = db.create_report(u1["id"], u3["id"], "Тестовая жалоба")
        assert created and report_id > 0
        assert db.get_user_by_id(u3["id"])["is_hidden"] == 0

        # Открытое обращение поддержки блокирует второе.
        tid = db.create_ticket(u1["id"], "question", "Вопрос")
        assert db.has_open_ticket(u1["id"]) is True
        db.close_ticket(tid, 999, "Ответ")
        assert db.has_open_ticket(u1["id"]) is False

        # Бан/разбан.
        db.ban_user(u2["id"], 7, "Тест", 999)
        assert db.is_banned(2)
        db.unban_user(u2["id"], 999)
        assert not db.is_banned(2)

        # Удаление профиля удаляет пользователя и связанные оценки/тикеты.
        tid2 = db.create_ticket(u3["id"], "idea", "Идея")
        assert db.delete_user(3) is True
        assert db.get_user(3) is None
        assert db.get_ticket(tid2) is None

        print("V2.1 smoke test: OK")


if __name__ == "__main__":
    main()
