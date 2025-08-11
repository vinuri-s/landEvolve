from PyQt6.QtSql import QSqlDatabase, QSqlQuery

class Database:
    # _instance = None
    # def __new__(cls, db_path="app_data.db"):
    #     if cls._instance is None:
    #         cls._instance = super(Database, cls).__new__(cls)
    #         cls._instance._initialized = False
    #     return cls._instance
    
    def __init__(self, db_path="db/app_data.db"):
        self.db = QSqlDatabase.addDatabase("QSQLITE")
        self.db.setDatabaseName(db_path)

        if not self.db.open():
            raise Exception("Failed to connect to database")

        self.create_tables()

    def create_tables(self):
        query = QSqlQuery()

        query.exec("""
            CREATE TABLE IF NOT EXISTS Location (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                satelite_image_path TEXT,
                description TEXT
            )
        """)

        query.exec("""
            CREATE TABLE IF NOT EXISTS GeoTiff (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id INTEGER NOT NULL,
                tiff_file_path TEXT NOT NULL,
                resolution TEXT,
                FOREIGN KEY (location_id) REFERENCES Location(id)
            )
        """)

        query.exec("""
            CREATE TABLE IF NOT EXISTS Component (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT
            )
        """)

        query.exec("""
            CREATE TABLE IF NOT EXISTS ComponentParam (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                component_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                FOREIGN KEY (component_id) REFERENCES Component(id)
            )
        """)

    def insert_location(self, name, satelite_image_path, description):
        query = QSqlQuery()
        query.prepare("""
            INSERT INTO Location (name, satelite_image_path, description)
            VALUES (?, ?, ?)
        """)
        query.addBindValue(name)
        query.addBindValue(satelite_image_path)
        query.addBindValue(description)
        query.exec()
        return query.lastInsertId()

    def fetch_locations(self):
        query = QSqlQuery("SELECT * FROM Location")
        results = []
        while query.next():
            results.append(
                (query.value(0), query.value(1), query.value(2), query.value(3))
            )
        print("\nAll Locations result:", len(results))
        return results

    def insert_geotiff(self, location_id, tiff_file_path, resolution):
        query = QSqlQuery()
        query.prepare("""
            INSERT INTO GeoTiff (location_id, tiff_file_path, resolution)
            VALUES (?, ?, ?)
        """)
        query.addBindValue(location_id)
        query.addBindValue(tiff_file_path)
        query.addBindValue(resolution)
        query.exec()
        return query.lastInsertId()

    def fetch_geotiffs(self):
        query = QSqlQuery("SELECT * FROM GeoTiff")
        results = []
        while query.next():
            results.append(
                (query.value(0), query.value(1), query.value(2), query.value(3))
            )
        return results

    def insert_component(self, name, description):
        query = QSqlQuery()
        query.prepare("""
            INSERT INTO Component (name, description)
            VALUES (?, ?)
        """)
        query.addBindValue(name)
        query.addBindValue(description)
        query.exec()
        return query.lastInsertId()

    def fetch_components(self):
        query = QSqlQuery("SELECT * FROM Component")
        results = []
        while query.next():
            results.append(
                (query.value(0), query.value(1), query.value(2))
            )
        return results

    def insert_component_param(self, component_id, key):
        query = QSqlQuery()
        query.prepare("""
            INSERT INTO ComponentParam (component_id, key)
            VALUES (?, ?)
        """)
        query.addBindValue(component_id)
        query.addBindValue(key)
        query.exec()
        return query.lastInsertId()

    def fetch_component_params(self):
        query = QSqlQuery("SELECT * FROM ComponentParam")
        results = []
        while query.next():
            results.append(
                (query.value(0), query.value(1), query.value(2))
            )
        return results

    def close(self):
        self.db.close()
