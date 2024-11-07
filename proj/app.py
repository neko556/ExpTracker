import tkinter as tk
from tkinter import messagebox, ttk
import sqlite3
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Connect to SQLite database
conn = sqlite3.connect('expense_tracker.db')
cursor = conn.cursor()

# Create tables if they don't exist
cursor.execute('''
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    category TEXT,
    amount REAL,
    description TEXT
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    total_income REAL
)
''')
conn.commit()

# Fetch or initialize total income
cursor.execute("SELECT total_income FROM income ORDER BY id DESC LIMIT 1")
income_row = cursor.fetchone()
total_income = income_row[0] if income_row else 1000

# Variables to hold selected category and month
selected_category = None

# Functions for operations
def update_income():
    global total_income
    try:
        total_income = float(total_income_entry.get())
        cursor.execute("INSERT INTO income (total_income) VALUES (?)", (total_income,))
        conn.commit()
        messagebox.showinfo("Income Updated", f"Total income set to ${total_income:.2f}")
        update_remaining_income_label()
    except ValueError:
        messagebox.showerror("Invalid Input", "Please enter a valid number for income.")

def add_expense():
    try:
        amount = float(amount_entry.get())
        if amount <= 0:
            messagebox.showerror("Invalid Amount", "Amount should be a positive number.")
            return

        date = datetime.today().strftime('%Y-%m-%d')
        category = category_combobox.get()
        description = description_entry.get()

        cursor.execute("INSERT INTO expenses (date, category, amount, description) VALUES (?, ?, ?, ?)",
                       (date, category, amount, description))
        conn.commit()
        clear_entries()
        
        update_remaining_income_label()
        view_expenses(selected_category)  # Refreshes view in the current selected category or all
        update_graph()

    except ValueError:
        messagebox.showerror("Invalid Input", "Amount should be a number.")

def delete_expense():
    selected_item = expense_tree.selection()
    if not selected_item:
        messagebox.showwarning("Select Item", "Please select an expense to delete.")
        return

    item = expense_tree.item(selected_item)
    expense_id = item["values"][0]
    cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    messagebox.showinfo("Deleted", "Expense deleted successfully!")
    update_remaining_income_label()
    view_expenses(selected_category)
    update_graph()

def update_remaining_income_label():
    cursor.execute("SELECT SUM(amount) FROM expenses")
    total_expenses = cursor.fetchone()[0] or 0
    remaining_income = total_income - total_expenses
    remaining_income_label.config(text=f"Remaining Income: ${remaining_income:.2f}")

def view_expenses(category=None):
    for row in expense_tree.get_children():
        expense_tree.delete(row)

    if category:
        cursor.execute("SELECT * FROM expenses WHERE category = ? AND strftime('%m', date) = ?", (category, datetime.today().strftime('%m')))
    else:
        cursor.execute("SELECT * FROM expenses WHERE strftime('%m', date) = ?", (datetime.today().strftime('%m'),))

    expenses = cursor.fetchall()
    for expense in expenses:
        expense_tree.insert("", "end", values=expense)

def update_graph():
    cursor.execute("SELECT category, SUM(amount) FROM expenses GROUP BY category")
    expenses_by_category = cursor.fetchall()

    categories = [expense[0] for expense in expenses_by_category]
    amounts = [expense[1] for expense in expenses_by_category]

    fig, ax = plt.subplots(figsize=(5, 4))
    colors = plt.cm.Paired(range(len(categories)))
    ax.bar(categories, amounts, color=colors)
    ax.set_title("Expenditure by Category")
    ax.set_xlabel("Category")
    ax.set_ylabel("Amount")

    for widget in graph_frame.winfo_children():
        widget.destroy()

    canvas = FigureCanvasTkAgg(fig, master=graph_frame)
    canvas.draw()
    canvas.get_tk_widget().pack()

def clear_entries():
    amount_entry.delete(0, tk.END)
    category_combobox.set('')
    description_entry.delete(0, tk.END)

def select_category(category):
    global selected_category
    selected_category = category
    view_expenses(category)

# Main GUI window
app = tk.Tk()
app.title("Expense Tracker")
app.geometry("900x600")

# Sidebar for categories
sidebar = tk.Frame(app, width=150)
sidebar.pack(side="left", fill="y")
sidebar_title = tk.Label(sidebar, text="Categories", font=("Arial", 14, "bold"))
sidebar_title.pack(pady=10)

categories = ["Food", "Transportation", "Entertainment", "Utilities", "Healthcare", "Miscellaneous"]
for category in categories:
    btn = tk.Button(sidebar, text=category, command=lambda c=category: select_category(c))
    btn.pack(fill="x", pady=5)

# Input frame for new expenses
input_frame = tk.Frame(app)
input_frame.pack(fill="x", pady=10)

tk.Label(input_frame, text="Category").grid(row=0, column=0, padx=5, pady=5)
category_combobox = ttk.Combobox(input_frame, values=categories, state="readonly")
category_combobox.grid(row=0, column=1)

tk.Label(input_frame, text="Amount").grid(row=1, column=0, padx=5, pady=5)
amount_entry = tk.Entry(input_frame)
amount_entry.grid(row=1, column=1)

tk.Label(input_frame, text="Description").grid(row=2, column=0, padx=5, pady=5)
description_entry = tk.Entry(input_frame)
description_entry.grid(row=2, column=1)

add_expense_button = tk.Button(input_frame, text="Add Expense", command=add_expense)
add_expense_button.grid(row=3, column=0, columnspan=2, pady=10)

delete_expense_button = tk.Button(input_frame, text="Delete Expense", command=delete_expense)
delete_expense_button.grid(row=3, column=2, pady=10)

# Total Income Input Section
tk.Label(input_frame, text="Total Income").grid(row=4, column=0, padx=5, pady=5)
total_income_entry = tk.Entry(input_frame)
total_income_entry.grid(row=4, column=1)
total_income_entry.insert(0, f"{total_income}")

update_income_button = tk.Button(input_frame, text="Update Income", command=update_income)
update_income_button.grid(row=4, column=2)

# Display Treeview for expenses
expense_tree = ttk.Treeview(app, columns=("ID", "Date", "Category", "Amount", "Description"), show="headings")
expense_tree.heading("ID", text="ID")
expense_tree.heading("Date", text="Date")
expense_tree.heading("Category", text="Category")
expense_tree.heading("Amount", text="Amount")
expense_tree.heading("Description", text="Description")
expense_tree.pack(fill="x", pady=10)

# Graph and Remaining Income
graph_frame = tk.Frame(app)
graph_frame.pack(fill="both", expand=True)

remaining_income_label = tk.Label(app, text=f"Remaining Income: ${total_income:.2f}")
remaining_income_label.pack(pady=10)

view_expenses()
update_remaining_income_label()

app.mainloop()
