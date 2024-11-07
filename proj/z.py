import tkinter as tk
from tkinter import messagebox, ttk
import sqlite3
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Connect to SQLite database
conn = sqlite3.connect('expense_tracker.db')
cursor = conn.cursor()

# Create expenses table if it doesn't exist
cursor.execute('''
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    category TEXT,
    amount REAL,
    description TEXT
)
''')
conn.commit()

# Budget limit
BUDGET = 1000

# Function to clear the graph if it exists
def clear_graph():
    for widget in expense_tracker_frame.winfo_children():
        if isinstance(widget, FigureCanvasTkAgg):
            widget.get_tk_widget().destroy()

# Function to validate date format (YYYY-MM-DD)
def validate_date(date_str):
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False

# Functions for expense operations
def add_expense():
    date = date_entry.get()
    if not validate_date(date):
        messagebox.showerror("Invalid Input", "Date should be in the format YYYY-MM-DD.")
        return
    
    category = category_combobox.get()
    if not category:
        messagebox.showerror("Invalid Input", "Category cannot be empty.")
        return
    
    try:
        amount = float(amount_entry.get())
    except ValueError:
        messagebox.showerror("Invalid Input", "Amount should be a number.")
        return
    
    description = description_entry.get()

    # Check if adding the expense exceeds the budget
    cursor.execute("SELECT SUM(amount) FROM expenses")
    total_expense = cursor.fetchone()[0] or 0
    if total_expense + amount > BUDGET:
        messagebox.showerror("Budget Exceeded", f"Adding this expense will exceed your budget of ${BUDGET}.")
        return

    cursor.execute("INSERT INTO expenses (date, category, amount, description) VALUES (?, ?, ?, ?)",
                   (date, category, amount, description))
    conn.commit()
    messagebox.showinfo("Success", "Expense added successfully!")

    # Disable Add Expense button to prevent accidental multiple submissions
    add_expense_button.config(state=tk.DISABLED)

    # Clear the input fields and refresh data
    clear_entries()
    update_graph()

    # Re-enable Add Expense button after successful submission
    add_expense_button.config(state=tk.NORMAL)

def view_expenses(category=None):
    for row in expense_tree.get_children():
        expense_tree.delete(row)

    if category:
        cursor.execute("SELECT * FROM expenses WHERE category = ?", (category,))
    else:
        cursor.execute("SELECT * FROM expenses")
    
    expenses = cursor.fetchall()
    for expense in expenses:
        expense_tree.insert("", "end", values=expense)

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
    
    # Refresh expense list and graph
    update_graph()

def clear_entries():
    date_entry.delete(0, tk.END)
    category_combobox.set('')  # Reset category dropdown
    amount_entry.delete(0, tk.END)
    description_entry.delete(0, tk.END)

def update_graph():
    cursor.execute("SELECT category, SUM(amount) FROM expenses GROUP BY category")
    expenses_by_category = cursor.fetchall()

    categories = [expense[0] for expense in expenses_by_category]
    amounts = [expense[1] for expense in expenses_by_category]

    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar(categories, amounts, color='skyblue')
    ax.set_title("Expenditure by Category")
    ax.set_xlabel("Category")
    ax.set_ylabel("Amount")

    canvas = FigureCanvasTkAgg(fig, master=expense_tracker_frame)
    canvas.draw()
    canvas.get_tk_widget().grid(row=5, column=0, columnspan=2, padx=10, pady=10)

    # Update Total Income (example: assume total income is 1000)
    total_income = total_income_entry.get() if total_income_entry.get() else 1000
    try:
        total_income = float(total_income)
    except ValueError:
        total_income = 1000  # Default value if input is invalid
    
    total_expense = sum(amounts)
    remaining_income = total_income - total_expense
    remaining_income_label.config(text=f"Remaining Income: ${remaining_income:.2f}")

def show_graph():
    clear_graph()  # Ensure no previous graph is shown
    update_graph()  # Create and show the graph
    show_graph_button.config(state=tk.DISABLED)  # Disable the "Show Graph" button
    hide_graph_button.config(state=tk.NORMAL)  # Enable the "Hide Graph" button

def hide_graph():
    clear_graph()  # Clear the graph
    show_graph_button.config(state=tk.NORMAL)  # Enable the "Show Graph" button
    hide_graph_button.config(state=tk.DISABLED)  # Disable the "Hide Graph" button

# Function to display expenses filtered by category when clicked
def filter_by_category(category):
    # Clear the existing expenses
    for row in expense_tree.get_children():
        expense_tree.delete(row)
    
    # Fetch and display expenses based on selected category
    view_expenses(category)

# Initialize the main window
app = tk.Tk()
app.title("Expense Tracker")
app.geometry("1000x600")

# Expense Tracker Frame
main_frame = tk.Frame(app)
main_frame.pack(fill="both", expand=True)

# Sidebar Frame for categories
sidebar_frame = tk.Frame(main_frame, width=200, bg="lightgray")
sidebar_frame.pack(side="left", fill="y")

# Add a label for the category sidebar
tk.Label(sidebar_frame, text="Categories", bg="lightgray", font=("Arial", 14)).pack(pady=10)

# List of categories (hardcoded for now)
categories = ["Food", "Transportation", "Entertainment", "Utilities", "Healthcare", "Miscellaneous"]

# Create buttons for each category in the sidebar
for category in categories:
    category_button = tk.Button(sidebar_frame, text=category, command=lambda c=category: filter_by_category(c), width=20)
    category_button.pack(pady=5)

# Expense Tracker Frame for input and data display
expense_tracker_frame = tk.Frame(main_frame)
expense_tracker_frame.pack(side="left", fill="both", expand=True)

# Input fields for new expenses
tk.Label(expense_tracker_frame, text="Date (System Date)").grid(row=0, column=0, padx=5, pady=5)
date_entry = tk.Entry(expense_tracker_frame)
date_entry.grid(row=0, column=1)
date_entry.insert(0, datetime.today().strftime('%Y-%m-%d'))

tk.Label(expense_tracker_frame, text="Category").grid(row=1, column=0, padx=5, pady=5)
category_combobox = ttk.Combobox(expense_tracker_frame, values=categories, state="readonly")
category_combobox.grid(row=1, column=1)
category_combobox.set(categories[0])

tk.Label(expense_tracker_frame, text="Amount").grid(row=2, column=0, padx=5, pady=5)
amount_entry = tk.Entry(expense_tracker_frame)
amount_entry.grid(row=2, column=1)

tk.Label(expense_tracker_frame, text="Description").grid(row=3, column=0, padx=5, pady=5)
description_entry = tk.Entry(expense_tracker_frame)
description_entry.grid(row=3, column=1)

# Add Expense button
add_expense_button = tk.Button(expense_tracker_frame, text="Add Expense", command=add_expense)
add_expense_button.grid(row=4, column=0, pady=10)

tk.Button(expense_tracker_frame, text="Delete Expense", command=delete_expense).grid(row=4, column=1, pady=10)

# Display area for expenses (Initially hidden)
expense_tree = ttk.Treeview(
    expense_tracker_frame,
    columns=("ID", "Date", "Category", "Amount", "Description"),
    show="headings"
)
expense_tree.heading("ID", text="ID")
expense_tree.heading("Date", text="Date")
expense_tree.heading("Category", text="Category")
expense_tree.heading("Amount", text="Amount")
expense_tree.heading("Description", text="Description")
expense_tree.grid(row=5, column=0, columnspan=2, padx=10, pady=10)
expense_tree.grid_forget()  # Hide the tree by default

# Label for displaying remaining income
remaining_income_label = tk.Label(expense_tracker_frame, text="Remaining Income: $1000")
remaining_income_label.grid(row=6, column=0, columnspan=2, padx=10, pady=10)

# Entry for Total Income (dynamic)
tk.Label(expense_tracker_frame, text="Total Income").grid(row=7, column=0, padx=5, pady=5)
total_income_entry = tk.Entry(expense_tracker_frame)
total_income_entry.grid(row=7, column=1)

# Show Graph button
show_graph_button = tk.Button(expense_tracker_frame, text="Show Graph", command=show_graph)
show_graph_button.grid(row=8, column=0, columnspan=2, pady=10)

# Hide Graph button
hide_graph_button = tk.Button(expense_tracker_frame, text="Hide Graph", command=hide_graph, state=tk.DISABLED)
hide_graph_button.grid(row=9, column=0, columnspan=2, pady=10)

# Load existing expenses at startup
view_expenses()

# Run the main loop
app.mainloop()

# Close database connection when app closes
conn.close()