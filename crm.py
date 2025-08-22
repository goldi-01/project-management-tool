import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from io import BytesIO
import zipfile
import re
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.message import EmailMessage

@st.cache_data(ttl=10)
def get_all_comments():
    with get_db_connection() as conn:
        return pd.read_sql("SELECT * FROM comments ORDER BY timestamp DESC", conn)

def get_db_connection():
    return sqlite3.connect("crm.db", timeout=30, check_same_thread=False)
# --- DATABASE SETUP ---
# Create new columns if not exist
with get_db_connection() as conn:
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE tasks ADD COLUMN sub_module TEXT")
        c.execute("ALTER TABLE tasks ADD COLUMN priority TEXT")
        c.execute("ALTER TABLE tasks ADD COLUMN deadline_date TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # columns already added



# Create tables if not exist
with get_db_connection() as conn:
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
                    email TEXT PRIMARY KEY,
                    password TEXT,
                    role TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assigned_to TEXT,
                    project_topic TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    status TEXT)""")
    conn.commit()


with get_db_connection() as conn:
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            user_email TEXT,
            comment TEXT,
            reply TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

# Default users
def create_default_users():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users VALUES (?,?,?)", ("admin@example.com", "admin123", "admin"))
        c.execute("INSERT OR IGNORE INTO users VALUES (?,?,?)", ("user@example.com", "user123", "user"))
        conn.commit()

create_default_users()


def send_email(to, subject, body):
    sender = "your_email@gmail.com"
    password = "xxxxxxxxxxxxxxxx"  # ← App password (not your Gmail login password)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.send_message(msg)
        print("Email sent successfully")
    except Exception as e:
        print("Email sending failed:", e)
# --- LOGIN FUNCTION ---
def login(email, password):
    c.execute("SELECT role FROM users WHERE email=? AND password=?", (email, password))
    result = c.fetchone()
    return result[0] if result else None
def safe_date(value):
    try:
        date_val = pd.to_datetime(value, errors="coerce")
        if pd.isna(date_val):
            return datetime.date.today()  # Default: today
        return date_val.date()
    except:
        return datetime.date.today()
# --- ADMIN PANEL ---
def admin_panel():
    st.subheader("Admin Panel - Manage Tasks and Users")
    # ---- Run one time only then comment
    # with get_db_connection() as conn:
    #     c = conn.cursor()
    #     try:
    #         c.execute("ALTER TABLE tasks ADD COLUMN name TEXT;")
    #         conn.commit()
    #         st.success("Column 'name' added to tasks table successfully.")
    #     except Exception as e:
    #         st.warning(f"Could not add column. Maybe it already exists. Error: {e}")

    # ----- USER MANAGEMENT -----
    with st.expander("👥 Manage Users"):
        st.write("### Add New User")
        with st.form("add_user"):
            new_email = st.text_input("Email")
            new_password = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", ["admin", "user"])
            submitted = st.form_submit_button("Add User")
            if submitted:
                email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
                if not re.match(email_pattern, new_email):
                    st.error("Please enter a valid email address.")
                else:
                    try:
                        with get_db_connection() as conn:
                            c = conn.cursor()
                            c.execute("INSERT INTO users VALUES (?,?,?)", (new_email, new_password, new_role))
                            conn.commit()
                        st.success("User added successfully!")
                        st.cache_data.clear()
                    except sqlite3.IntegrityError:
                        st.error("User already exists.")

        st.write("### Existing Users")
        with get_db_connection() as conn:
            users_df = pd.read_sql("SELECT * FROM users", conn)
        st.dataframe(users_df, use_container_width=True, height=150)

        del_user = st.selectbox("Select user to delete", users_df["email"])
        if st.button("Delete Selected User"):
            if del_user != "admin@example.com":
                with get_db_connection() as conn:
                    c = conn.cursor()
                    c.execute("DELETE FROM users WHERE email=?", (del_user,))
                    conn.commit()
                st.success(f"User {del_user} deleted.")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Default admin cannot be deleted.")

    # ----- CHANGE PASSWORD -----
    with st.expander("🔑 Change User Password"):
        with get_db_connection() as conn:
            user_emails_df = pd.read_sql("SELECT email FROM users", conn)
        change_email = st.selectbox("Select User", user_emails_df["email"].tolist())
        new_password = st.text_input("New Password", type="password")
        if st.button("Update Password"):
            if new_password.strip() == "":
                st.error("Password cannot be empty.")
            else:
                with get_db_connection() as conn:
                    c = conn.cursor()
                    c.execute("UPDATE users SET password=? WHERE email=?", (new_password, change_email))
                    conn.commit()
                st.success(f"Password updated successfully for {change_email}")
                st.cache_data.clear()
                st.rerun()

    # ----- TASK MANAGEMENT -----
    with st.expander("➕ Add New Task"):
        # 👇 Checkbox outside form with unique key
        completion_set = st.checkbox("Set Completion Date?", key="add_completion_checkbox")
        end_date = None
        if completion_set:
            end_date_input = st.date_input(
                "Completion Date (if Completed)",
                value=datetime.date.today(),
                key="add_completion_date"
            )
            end_date = str(end_date_input)

        # 👇 Start the form after checkbox
        with st.form("add_task"):
            with get_db_connection() as conn:
                user_emails = pd.read_sql("SELECT email FROM users WHERE role != 'admin'", conn)["email"].tolist()

            if not user_emails:
                st.warning("No users available. Please add users first.")
            else:
                task_id = st.text_input("Task ID (Enter manually)")
                assignee_name = st.text_input("Assignee Name")
                assigned_to = st.selectbox("Assign To", user_emails)
                project_topic = st.text_input("Project Topic")
                start_date = st.date_input("Start Date")
                deadline_date = st.date_input("Deadline Date")
                status = st.selectbox("Status", ["Started", "Progressing", "Completed", "Incomplete"])
                sub_module_options = ["Research", "Dependencies Install", "Project Code Started", "Completed"]
                sub_module = "Completed" if status == "Completed" else st.selectbox("Sub Module", sub_module_options)
                priority = st.selectbox("Priority", ["High", "Medium", "Low"])

                submitted = st.form_submit_button("Add Task")

                if submitted:
                    if not task_id.strip():
                        st.error("Please enter a Task ID.")
                    elif not assigned_to:
                        st.error("Please select at least one user.")
                    elif not project_topic.strip():
                        st.error("Please enter a Project Topic.")
                    else:
                        try:
                            with get_db_connection() as conn:
                                c = conn.cursor()
                                completion = end_date if completion_set else None
                                c.execute("""
                                    INSERT INTO tasks (id, assigned_to, name, project_topic, start_date, end_date, status, sub_module, priority, deadline_date)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    task_id, assigned_to, assignee_name.strip(), project_topic, str(start_date),
                                    completion, status, sub_module, priority, str(deadline_date)
                                ))
                                conn.commit()
                            st.success(f"Task assigned to {assigned_to} successfully!")
                        except sqlite3.IntegrityError:
                            st.error(f"Task ID '{task_id}' already exists. Please use a unique ID.")



  


    # Load all tasks
    with get_db_connection() as conn:
        tasks = pd.read_sql("SELECT * FROM tasks", conn)
    st.write("### All Tasks")
    st.dataframe(tasks, use_container_width=True, height=200)

    if tasks.empty:
        st.warning("No data available.")
        return

    # --- TASK EDIT & DELETE ---
    
    with st.expander("✏️ Edit or Delete Tasks"):
        task_ids = tasks["id"].tolist()
        selected_task_id = st.selectbox("Select Task ID", task_ids)

        selected_task = tasks[tasks["id"] == selected_task_id].iloc[0]
        new_task_id = st.text_input("Task ID", value=str(selected_task["id"]))
        new_name = st.text_input("Assignee Name", value=selected_task["name"])
        new_assigned = st.text_input("Assigned To (Email)", value=selected_task["assigned_to"])
        new_topic = st.text_input("Project Topic", value=selected_task["project_topic"])
        new_start = st.date_input(
            "Start Date",
            value=pd.to_datetime(selected_task["start_date"], errors="coerce").date()
            if pd.notnull(selected_task["start_date"]) else datetime.date.today()
        )

        # Checkbox for completion date
        completion_set_update = st.checkbox(
            "Set Completion Date?",
            value=pd.notnull(pd.to_datetime(selected_task["end_date"], errors="coerce")),
            key=f"edit_completion_checkbox_{selected_task['id']}"
        )
        new_end = None
        if completion_set_update:
            existing_end = pd.to_datetime(selected_task["end_date"], errors="coerce")
            new_end_input = st.date_input(
                "Completion Date (if Completed)",
                value=existing_end.date() if pd.notnull(existing_end) else datetime.date.today(),
                key=f"edit_completion_date_{selected_task['id']}"
            )
            new_end = str(new_end_input)


        new_deadline = st.date_input(
            "Deadline Date",
            value=pd.to_datetime(selected_task["deadline_date"], errors="coerce").date()
            if pd.notnull(selected_task["deadline_date"]) else datetime.date.today()
        )

        new_status = st.selectbox(
            "Status",
            ["Started", "Progressing", "Incomplete", "Completed"],
            index=["Started", "Progressing", "Incomplete", "Completed"].index(selected_task["status"])
            if selected_task["status"] in ["Started", "Progressing", "Incomplete", "Completed"] else 0
        )

        sub_module_options = ["Research", "Dependencies Install", "Project Code Started", "Completed"]
        if new_status == "Completed":
            new_sub_module = "Completed"
        else:
            default_sub_index = (
                sub_module_options.index(selected_task["sub_module"])
                if selected_task["sub_module"] in sub_module_options else 0
            )
            new_sub_module = st.selectbox("Sub Module", sub_module_options, index=default_sub_index)

        new_priority = st.selectbox(
            "Priority",
            ["High", "Medium", "Low"],
            index=["High", "Medium", "Low"].index(selected_task["priority"])
            if selected_task["priority"] in ["High", "Medium", "Low"] else 0
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Update Task"):
                with get_db_connection() as conn:
                    c = conn.cursor()
                    c.execute("SELECT * FROM users WHERE email=?", (new_assigned,))
                    if c.fetchone() is None:
                        st.error("Assigned email does not exist in users table!")
                    else:
                        # ✅ Use checkbox condition, not status
                        completion = new_end if completion_set_update else None
                        try:
                            c.execute("""
                                UPDATE tasks 
                                SET id=?, assigned_to=?, name=?, project_topic=?, start_date=?, end_date=?, 
                                    deadline_date=?, status=?, sub_module=?, priority=? 
                                WHERE id=?
                            """, (
                                new_task_id, new_assigned, new_name.strip(), new_topic, str(new_start), completion,
                                str(new_deadline), new_status, new_sub_module, new_priority, selected_task_id
                            ))
                            conn.commit()
                            st.success("Task updated successfully!")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error(f"Task ID '{new_task_id}' already exists. Please use a unique ID.")

        with col2:
            if st.button("Delete Task"):
                with get_db_connection() as conn:
                    c = conn.cursor()
                    c.execute("DELETE FROM tasks WHERE id=?", (selected_task_id,))
                    conn.commit()
                    st.success("Task deleted successfully!")
                    st.rerun()




    # Convert dates
    for col in ["start_date", "end_date"]:
        tasks[col] = pd.to_datetime(tasks[col], errors="coerce")

    # --- FILTERS ---
    st.sidebar.header("Filters")
    filters = {
        "Assignee": st.sidebar.multiselect("Filter by Assignee", tasks["assigned_to"].dropna().unique()),
        "Project Topic": st.sidebar.multiselect("Filter by Project Topic", tasks["project_topic"].dropna().unique()),
        "Status": st.sidebar.multiselect("Filter by Status", tasks["status"].dropna().unique()),
        "Priority": st.sidebar.multiselect("Filter by Priority", tasks["priority"].dropna().unique()),
        "Sub Module": st.sidebar.multiselect("Filter by Sub Module", tasks["sub_module"].dropna().unique())
    }

    filtered = tasks.copy()
    for key, selected in filters.items():
        if selected:
            if key == "Assignee":
                filtered = filtered[filtered["assigned_to"].isin(selected)]
            elif key == "Project Topic":
                filtered = filtered[filtered["project_topic"].isin(selected)]
            elif key == "Status":
                filtered = filtered[filtered["status"].isin(selected)]
            elif key == "Priority":
                filtered = filtered[filtered["priority"].isin(selected)]
            elif key == "Sub Module":
                filtered = filtered[filtered["sub_module"].isin(selected)]

    if filtered.empty:
        st.warning("No tasks match selected filters.")
        return

    # --- METRICS ---
    total = len(filtered)
    completed = len(filtered[filtered["status"].str.lower() == "completed"])
    pending = len(filtered[~filtered["status"].str.lower().isin(["completed"])])
    progress = (completed / total) * 100 if total else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Tasks", total)
    c2.metric("Completed", completed)
    c3.metric("Pending", pending)
    c4.metric("Progress", f"{progress:.1f}%")


    # --- CHARTS (Compact Dashboard Layout) ---
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)
    chart_images = {}

    # Bar Chart - Tasks by Assignee (Scrollable if many assignees)
    with col1:
        data = filtered.groupby("assigned_to")["id"].count().reset_index()
        fig1 = px.bar(
            data,
            x="assigned_to",
            y="id",
            title="Tasks by Assignee",
            text_auto=True
        )
        fig1.update_layout(
            xaxis={'categoryorder': 'total descending'},
            height=400,
            xaxis_tickangle=-45
        )
        if len(data) > 10:  # Agar assignee zyada hain to scroll
            fig1.update_layout(xaxis=dict(tickmode='linear', tickfont=dict(size=10)), height=600)
        st.plotly_chart(fig1, use_container_width=True)
        chart_images["Bar_Chart.png"] = fig1.to_image(format="png")

    # Pie Chart - Task Status Distribution
    with col2:
        status_counts = filtered["status"].value_counts().reset_index()
        status_counts.columns = ["status", "count"]
        fig2 = px.pie(
            status_counts,
            names="status",
            values="count",
            title="Task Status Distribution"
        )
        st.plotly_chart(fig2, use_container_width=True)
        chart_images["Pie_Chart.png"] = fig2.to_image(format="png")

    # Line Chart - Completed Tasks Over Time
    # Line Chart - Completed Tasks Over Time
    with col3:
        completed_time = (
            filtered[filtered["status"].str.lower() == "completed"]
            .copy()
        )
        completed_time["end_date"] = pd.to_datetime(completed_time["end_date"], errors="coerce")
        completed_time = (
            completed_time.groupby(completed_time["end_date"].dt.strftime("%Y-%m"))["id"]
            .count()
            .reset_index()
        )
        completed_time.columns = ["Month", "Completed Tasks"]
        fig3 = px.line(completed_time, x="Month", y="Completed Tasks",
                    title="Completed Tasks Over Time", markers=True)
        fig3.update_xaxes(title_text="Month")
        st.plotly_chart(fig3, use_container_width=True)
        chart_images["Line_Chart.png"] = fig3.to_image(format="png")

    # Progress Over Time - Cumulative Completed Percentage
    with col4:
        sorted_df = filtered.copy()
        sorted_df["end_date"] = pd.to_datetime(sorted_df["end_date"], errors="coerce")
        sorted_df = sorted_df.sort_values("end_date")
        sorted_df["Month"] = sorted_df["end_date"].dt.strftime("%Y-%m")
        sorted_df["cumulative_completed"] = (sorted_df["status"].str.lower() == "completed").cumsum()
        sorted_df["Progress %"] = sorted_df["cumulative_completed"] / total * 100
        fig4 = px.line(sorted_df, x="Month", y="Progress %", title="Progress Over Time", markers=True)
        fig4.update_xaxes(title_text="Month")
        st.plotly_chart(fig4, use_container_width=True)
        chart_images["Progress_Chart.png"] = fig4.to_image(format="png")



    # --- EXPORT ZIP ---
    st.write("### Export Summary + Charts")
    summary = pd.DataFrame({
        "Metric": ["Total Tasks", "Completed Tasks", "Pending Tasks", "Progress %"],
        "Value": [total, completed, pending, f"{progress:.1f}%"]
    })

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        excel_buf = BytesIO()
        with pd.ExcelWriter(excel_buf, engine="xlsxwriter") as writer:
            filtered.to_excel(writer, index=False, sheet_name="Filtered Data")
            summary.to_excel(writer, index=False, sheet_name="Summary")
        z.writestr("CRM_Data_Summary.xlsx", excel_buf.getvalue())
        for name, img in chart_images.items():
            z.writestr(name, img)

    st.download_button("Download Data + Charts (ZIP)", buffer.getvalue(),
                       "CRM_Dashboard_Data_Charts.zip", "application/zip")
    


    st.subheader("✉️ Send Direct Comment to User")

    # Fetch users and task IDs
    with get_db_connection() as conn:
        users = pd.read_sql("SELECT DISTINCT assigned_to FROM tasks", conn)
        tasks = pd.read_sql("SELECT DISTINCT id FROM tasks", conn)

    if not users.empty and not tasks.empty:
        selected_user = st.selectbox(
            "Select User", users['assigned_to'], key="send_comment_user_selector_unique"
        )
        selected_task = st.selectbox(
            "Select Task ID", tasks['id'], key="send_comment_task_selector_unique"
        )
        admin_comment = st.text_area(
            "Your Message (visible to user)", key="send_comment_text_unique"
        )

        if st.button("Send Comment", key="send_comment_btn_unique"):
            if admin_comment.strip():
                with get_db_connection() as conn:
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO comments (task_id, user_email, comment)
                        VALUES (?, ?, ?)
                    """, (selected_task, selected_user, admin_comment.strip()))
                    conn.commit()
                st.success("Comment sent to user successfully!")
            else:
                st.warning("Comment cannot be empty.")

    st.subheader("📬 Task Comments from Users")

# Refresh only comment section
    if st.button("🔄 Refresh Comments Only"):
        st.session_state.refresh_comments = True

    # Initialize session state if not set
    if "refresh_comments" not in st.session_state or st.session_state.refresh_comments:

        with get_db_connection() as conn:
            comments = pd.read_sql("SELECT * FROM comments ORDER BY timestamp DESC", conn)

        if comments.empty:
            st.info("No comments found yet.")
        else:
            for _, row in comments.iterrows():
                st.markdown(f"**🆔 Task ID**: {row['task_id']}")
                st.markdown(f"**👤 User**: {row['user_email']}")
                st.markdown(f"**💬 Comment**: {row['comment']}")
                st.markdown(f"**⏰ Time**: {row['timestamp']}")
                if row["reply"]:
                    st.markdown(f"**✅ Your Reply**: {row['reply']}")

                # Reply input
                reply = st.text_input(
                    f"Reply to {row['user_email']} for Task {row['task_id']}",
                    key=f"reply_{row['id']}"
                )

                if st.button(f"Send Reply", key=f"send_reply_{row['id']}"):
                    with get_db_connection() as conn:
                        c = conn.cursor()
                        c.execute("UPDATE comments SET reply=? WHERE id=?", (reply, row['id']))
                        conn.commit()
                    send_email(
                        row['user_email'],
                        f"Reply to your comment on Task {row['task_id']}",
                        reply
                    )
                    st.success("Reply sent!")
                    st.session_state.refresh_comments = True
                    st.rerun()

                # 🗑️ Delete comment
                if st.button("🗑️ Delete Comment", key=f"delete_comment_{row['id']}"):
                    with get_db_connection() as conn:
                        c = conn.cursor()
                        c.execute("DELETE FROM comments WHERE id=?", (row['id'],))
                        conn.commit()
                    st.success("Comment deleted.")
                    st.cache_data.clear()
                    st.rerun()

# --- USER PANEL ---
def user_panel(email):
    st.subheader("User Panel - My Tasks")

    with get_db_connection() as conn:
        tasks = pd.read_sql("SELECT * FROM tasks WHERE assigned_to=?", conn, params=(email,))
    st.dataframe(tasks, use_container_width=True, height=250)

    if not tasks.empty:
        task_id = st.selectbox("Select Task to Update", tasks["id"])
        selected_task = tasks[tasks["id"] == task_id].iloc[0]

        # ✅ Checkbox for end date
        completion_checkbox = st.checkbox(
            "Set Completion Date?",
            value=pd.notnull(pd.to_datetime(selected_task["end_date"], errors="coerce")),
            key=f"user_completion_checkbox_{task_id}"
        )

        new_end_date = None
        if completion_checkbox:
            existing_end = pd.to_datetime(selected_task["end_date"], errors="coerce")
            new_end_input = st.date_input(
                "Completion Date (if Completed)",
                value=existing_end.date() if pd.notnull(existing_end) else datetime.date.today(),
                key=f"user_completion_date_{task_id}"
            )
            new_end_date = str(new_end_input)

        # ✅ Form for task update
        with st.form("update_task_form"):
            new_status = st.selectbox("New Status", ["Started", "Progressing", "Completed", "Incomplete"])
            new_sub_module = st.selectbox("Sub Module", ["Research", "Dependencies Install", "Project Code Started", "Completed"])
            new_priority = st.selectbox("Priority", ["High", "Medium", "Low"])
            submitted = st.form_submit_button("Update Task")

        if submitted:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE tasks
                    SET status = ?, sub_module = ?, priority = ?, end_date = ?
                    WHERE id = ?
                """, (
                    new_status,
                    new_sub_module,
                    new_priority,
                    new_end_date if completion_checkbox else None,
                    task_id
                ))
                conn.commit()

            st.success("Task updated successfully!")
            st.rerun()

    # 💬 Add Comment to Admin
    if not tasks.empty:
        st.divider()
        st.subheader("💬 Add Comment to Admin")
        comment_task_id = st.selectbox("Select Task to Comment", tasks["id"], key="comment_task_selector")
        user_comment = st.text_area("Add a comment (visible to admin)", key="user_comment_text")
        if st.button("Submit Comment", key="submit_comment_button"):
            if user_comment.strip():
                with get_db_connection() as conn:
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO comments (task_id, user_email, comment)
                        VALUES (?, ?, ?)
                    """, (comment_task_id, email, user_comment.strip()))
                    conn.commit()
                st.success("Comment submitted successfully!")
                st.rerun()
            else:
                st.warning("Comment cannot be empty.")

    # 📨 Admin Replies and Comments
    st.subheader("📨 Admin Comments and Replies")

    if st.button("🔄 Refresh My Comments"):
        st.rerun()

    with get_db_connection() as conn:
        all_comments = pd.read_sql(
            "SELECT * FROM comments WHERE user_email=? ORDER BY timestamp DESC",
            conn,
            params=(email,)
        )

    if all_comments.empty:
        st.info("No comments yet.")
    else:
        for _, row in all_comments.iterrows():
            st.markdown(f"**🆔 Task ID**: {row['task_id']}")
            st.markdown(f"**💬 Comment**: {row['comment']}")

            if row["reply"]:
                st.markdown(f"**✅ Admin Reply**: {row['reply']}")

            st.markdown(f"*⏰ Time*: {row['timestamp']}")

            if row["user_email"] == email:
                if st.button("🗑️ Delete Comment", key=f"user_delete_{row['id']}"):
                    with get_db_connection() as conn:
                        c = conn.cursor()
                        c.execute("DELETE FROM comments WHERE id=?", (row['id'],))
                        conn.commit()
                    st.success("Comment deleted successfully.")
                    st.rerun()

            st.markdown("---")
# --- MAIN APP ---
def main():
    st.title("Project management")

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            role = login(email, password)
            if role:
                st.session_state["logged_in"] = True
                st.session_state["email"] = email
                st.session_state["role"] = role
            else:
                st.error("Invalid credentials")
    else:
        st.success(f"Logged in as {st.session_state['email']} ({st.session_state['role']})")
        
        # ---- Logout Button ----
        if st.button("Logout"):
            st.session_state["logged_in"] = False
            st.rerun()


        if st.session_state["role"] == "admin":
            admin_panel()
        else:
            user_panel(st.session_state["email"])


if __name__ == "__main__":
    main()
 