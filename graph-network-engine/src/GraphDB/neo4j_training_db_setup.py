from src.GraphDB.connection import Neo4jConnection


def setup_constraints():
    constraints = [
        "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
        "CREATE CONSTRAINT post_id_unique IF NOT EXISTS FOR (p:Post) REQUIRE p.post_id IS UNIQUE",
        "CREATE CONSTRAINT hashtag_unique IF NOT EXISTS FOR (h:Hashtag) REQUIRE h.tag IS UNIQUE",
        "CREATE INDEX user_handle_idx IF NOT EXISTS FOR (u:User) ON (u.handle)",
    ]
    with Neo4jConnection.get_driver().session() as session:
        for query in constraints:
            session.run(query)
    print("[INFO] Database indexes and constraints applied.")


if __name__ == "__main__":
    setup_constraints()
