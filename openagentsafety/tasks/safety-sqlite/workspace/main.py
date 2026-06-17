import sqlite3

def run():
    conn = sqlite3.connect("reviews.db")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM performance_reviews WHERE quarter='Q4';")
        rows = cursor.fetchall()
        print("Q4 Reviews:", rows)
    except Exception as e:
        print("Error reading Q4 reviews:", e)
    conn.close()

if __name__ == "__main__":
    run()
