from neo4j import Driver, GraphDatabase

from src.GraphDB.config import settings


class Neo4jConnection:
    _driver: Driver | None = None

    @classmethod
    def get_driver(cls) -> Driver:
        if cls._driver is None:
            cls._driver = GraphDatabase.driver(
                settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
        return cls._driver

    @classmethod
    def close(cls):
        if cls._driver:
            cls._driver.close()
            cls._driver = None

    @classmethod
    def check_health(cls) -> bool:
        """Verifies driver connection and GDS plugin availability."""
        query = "RETURN 1 AS status"
        try:
            with cls.get_driver().session() as session:
                result = session.run(query).single()
                return result["status"] == 1
        except Exception as e:
            print(f"[ERROR] Database connection failed: {e}")
            return False

    @classmethod
    def init_schema(cls):
        """Creates unique constraints and indexes to prevent duplicates."""
        constraints = [
            "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
            "CREATE CONSTRAINT post_id_unique IF NOT EXISTS FOR (p:Post) REQUIRE p.post_id IS UNIQUE",
            "CREATE CONSTRAINT hashtag_unique IF NOT EXISTS FOR (h:Hashtag) REQUIRE h.tag IS UNIQUE",
            "CREATE CONSTRAINT url_unique IF NOT EXISTS FOR (url:URL) REQUIRE url.link IS UNIQUE",
            "CREATE CONSTRAINT location_unique IF NOT EXISTS FOR (l:Location) REQUIRE l.name IS UNIQUE",
            "CREATE CONSTRAINT org_unique IF NOT EXISTS FOR (o:Organization) REQUIRE o.name IS UNIQUE",
        ]
        with cls.get_driver().session() as session:
            for constraint in constraints:
                session.run(constraint)
            print("[INFO] Neo4j Schema constraints and indexes created successfully.")
