"""Query helpers for the `reviews` table."""

from __future__ import annotations

from bot.database.core import Database

REVIEW_STATUSES = ("pending", "approved", "rejected", "hidden")


async def create_review(
    db: Database,
    order_id: int,
    product_id: int,
    user_id: int,
    rating: int,
    review_text: str | None,
    anonymous: bool,
) -> int:
    return await db.execute(
        """
        INSERT INTO reviews (order_id, product_id, user_id, rating, review_text, anonymous)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (order_id, product_id, user_id, rating, review_text, int(anonymous)),
    )


async def update_review(db: Database, review_id: int, **fields) -> None:
    allowed = {"rating", "review_text", "anonymous", "status"}
    sets, params = [], []
    for key, value in fields.items():
        if key not in allowed:
            continue
        sets.append(f"{key} = ?")
        params.append(value)
    if not sets:
        return
    sets.append("updated_at = datetime('now')")
    params.append(review_id)
    await db.execute(f"UPDATE reviews SET {', '.join(sets)} WHERE id = ?", tuple(params))


async def delete_review(db: Database, review_id: int) -> None:
    await db.execute("DELETE FROM reviews WHERE id = ?", (review_id,))


async def set_review_status(db: Database, review_id: int, status: str) -> None:
    await db.execute(
        "UPDATE reviews SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, review_id),
    )


async def get_review(db: Database, review_id: int):
    return await db.fetchone("SELECT * FROM reviews WHERE id = ?", (review_id,))


async def get_review_by_order(db: Database, order_id: int):
    return await db.fetchone("SELECT * FROM reviews WHERE order_id = ?", (order_id,))


async def list_reviews_for_product(
    db: Database, product_id: int, status: str = "approved", limit: int = 10, offset: int = 0
):
    return await db.fetchall(
        """
        SELECT * FROM reviews WHERE product_id = ? AND status = ?
        ORDER BY created_at DESC LIMIT ? OFFSET ?
        """,
        (product_id, status, limit, offset),
    )


async def list_reviews_for_user(db: Database, user_id: int):
    return await db.fetchall(
        "SELECT * FROM reviews WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    )


async def list_pending_reviews(db: Database, limit: int = 25):
    return await db.fetchall(
        "SELECT * FROM reviews WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
        (limit,),
    )


async def get_rating_summary(db: Database, product_id: int) -> dict:
    rows = await db.fetchall(
        "SELECT rating FROM reviews WHERE product_id = ? AND status = 'approved'",
        (product_id,),
    )
    distribution = {i: 0 for i in range(1, 6)}
    for row in rows:
        distribution[row["rating"]] = distribution.get(row["rating"], 0) + 1
    total = len(rows)
    average = (sum(r["rating"] for r in rows) / total) if total else 0.0
    return {"average": round(average, 2), "total": total, "distribution": distribution}
