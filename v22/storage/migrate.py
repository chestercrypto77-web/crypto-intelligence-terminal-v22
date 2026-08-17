from v22.brain.config import SETTINGS
from v22.storage.database import Database
def main():
    db=Database(SETTINGS.database_url); db.migrate(); print("V22 database migration complete")
if __name__=="__main__": main()
