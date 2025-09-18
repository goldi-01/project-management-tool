import streamlit as st
import pandas as pd
import datetime
import re
from pymongo import MongoClient
from bson.objectid import ObjectId

# Custom CSS for heading
st.markdown("""
    <style>
    .custom-heading {
        background-color: #1E3A8A;                  
        border-radius: 8px;
        text-align: center;
    }
    </style>
""", unsafe_allow_html=True)



# ---------- DB CONNECTION ----------
client = MongoClient("mongodb+srv://admin123:admin123@datascienceanywhere.vto1pi1.mongodb.net/") 
db = client["crm_final"]  
users_col = db["users"]
tasks_col = db["tasks"]
task_hours_col = db["task_hours"]

# ---------- EMAIL VALIDATION ----------
def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# ---------- DEFAULT DATA ----------
def setup_database():
    if users_col.count_documents({}) == 0:
        users_col.insert_many([
            {"email": "admin@example.com", "password": "admin123", "role": "admin"},
            {"email": "subadmin@example.com", "password": "sub123", "role": "subadmin"},
            {"email": "user@example.com", "password": "user123", "role": "user"},
        ])
setup_database()

# ---------- LOGIN ----------
def login(email, password):
    user = users_col.find_one({"email": email, "password": password})
    return user["role"] if user else None

# ---------- GET TASKS ----------
@st.cache_data(ttl=10)
def get_tasks(user_email=None):
    match_stage = {}
    if user_email:
        match_stage = {"assigned_to": user_email}

    tasks = list(tasks_col.aggregate([
        {"$match": match_stage},
        {"$lookup": {
            "from": "task_hours",
            "localField": "_id",
            "foreignField": "task_id",
            "as": "hours"
        }},
        {"$addFields": {
            "total_hours_spent": {"$sum": "$hours.hours_spent"}
        }}
    ]))

    
    for task in tasks:
        task["_id"] = str(task["_id"])   
        if "hours" in task:
            del task["hours"]           

    return pd.DataFrame(tasks)

# ---------- ADMIN PANEL ----------
def admin_panel():
    st.markdown("<h2 class='custom-heading'>Admin Panel - Manage Users & Tasks</h2>", unsafe_allow_html=True)

    # ---------------- Users Management ----------------
    st.subheader("👥 Manage Users")
    with st.expander("Add New User"):
        with st.form("add_user"):
            new_email = st.text_input("Email")
            new_password = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", ["admin", "subadmin", "user"])
            submitted = st.form_submit_button("Add User")
            if submitted:
                if not new_email or not new_password:
                    st.error("Email and Password required")
                elif not is_valid_email(new_email):
                    st.error("Please enter a valid email address")
                else:
                    if users_col.find_one({"email": new_email}):
                        st.error("User already exists!")
                    else:
                        users_col.insert_one({"email": new_email, "password": new_password, "role": new_role})
                        st.success(f"User {new_email} added successfully!")

        # Show Users Table
        users_df = pd.DataFrame(list(users_col.find({}, {"_id": 0})))
        st.dataframe(users_df)

        # Delete User
        if not users_df.empty:
            del_user = st.selectbox("Select user to delete", users_df["email"])
            if st.button("Delete Selected User"):
                if del_user == "admin@example.com":
                    st.error("Default admin cannot be deleted")
                else:
                    users_col.delete_one({"email": del_user})
                    st.success(f"User {del_user} deleted!")
                    st.rerun()

    # Change Password
    st.subheader("🔑 Change Password")
    with st.expander("Change Password"):
        user_emails = [u["email"] for u in users_col.find({}, {"email": 1})]
        change_email = st.selectbox("Select User", user_emails)
        new_pass = st.text_input("New Password", type="password")
        if st.button("Update Password"):
            if new_pass.strip() == "":
                st.error("Password cannot be empty")
            else:
                users_col.update_one({"email": change_email}, {"$set": {"password": new_pass}})
                st.success(f"Password updated for {change_email}")
                st.rerun()

    # ---------------- Tasks Management ----------------
    st.subheader("➕ Add New Task")
    with st.expander("Add New Task"):
        user_emails = [u["email"] for u in users_col.find({"role": "user"}, {"email": 1})]

        with st.form("add_task"):
            assigned_to = st.selectbox("Assign To", user_emails)
            project_name = st.text_input("Project Name")
            expected_hours = st.number_input("Expected Hours", min_value=0.0)
            status = st.selectbox("Status", ["Started", "Progressing", "Completed", "Incomplete"])
            department = st.selectbox("Department", ["Sales", "Accounts", "HR", "Marketing", "IT"])
            remark = st.selectbox("Remark", ["Green Flag", "Red Flag"])

            submitted = st.form_submit_button("Add Task")
            if submitted:
                if not project_name.strip():
                    st.error("Project Name required")
                else:
                    tasks_col.insert_one({
                        "assigned_to": assigned_to,
                        "project_name": project_name,
                        "expected_hours": expected_hours,
                        "status": status,
                        "department": department,
                        "remark": remark,
                        "message": ""
                    })
                    st.success(f"Task for {project_name} assigned to {assigned_to}")

    # Show All Tasks
    tasks_df = get_tasks()
    st.dataframe(tasks_df)

    # Edit/Delete Task
    st.subheader("✏️ Edit / Delete Task")
    if not tasks_df.empty:
        task_ids = tasks_df["_id"].tolist()
        selected_task_id = st.selectbox("Select Task ID", task_ids)
        selected_task = tasks_col.find_one({"_id": ObjectId(selected_task_id)})

        with st.form(f"edit_task_form_{selected_task_id}"):
            user_emails = [u["email"] for u in users_col.find({"role": "user"}, {"email": 1})]

            new_assigned = st.selectbox("Assign To", user_emails,
                                        index=user_emails.index(selected_task["assigned_to"]) if selected_task["assigned_to"] in user_emails else 0)
            new_project = st.text_input("Project Name", value=selected_task.get("project_name", ""))
            new_expected_hours = st.number_input("Expected Hours", value=float(selected_task.get("expected_hours", 0.0)))
            new_status = st.selectbox("Status", ["Started", "Progressing", "Completed", "Incomplete"],
                                      index=["Started","Progressing","Completed","Incomplete"].index(selected_task.get("status","Started")))
            departments = ["Sales", "Accounts", "HR", "Marketing", "IT"]
            current_dept = selected_task.get("department", "Sales")
            dept_index = departments.index(current_dept) if current_dept in departments else 0
            new_department = st.selectbox("Department", departments, index=dept_index)
            new_remark = st.selectbox("Remark", ["Green Flag","Red Flag"],
                                      index=["Green Flag","Red Flag"].index(selected_task.get("remark","Green Flag")))

            col1, col2 = st.columns(2)
            with col1:
                update_submitted = st.form_submit_button("Update Task")
            with col2:
                delete_submitted = st.form_submit_button("Delete Task")

            if update_submitted:
                tasks_col.update_one(
                    {"_id": ObjectId(selected_task_id)},
                    {"$set": {
                        "assigned_to": new_assigned,
                        "project_name": new_project,
                        "expected_hours": new_expected_hours,
                        "status": new_status,
                        "department": new_department,
                        "remark": new_remark
                    }}
                )
                st.success("Task updated successfully!")
                st.rerun()

            if delete_submitted:
                tasks_col.delete_one({"_id": ObjectId(selected_task_id)})
                task_hours_col.delete_many({"task_id": ObjectId(selected_task_id)})
                st.success("Task deleted successfully!")
                st.rerun()

# ---------- SUBADMIN PANEL ----------
def subadmin_panel(user_email):
    st.markdown("<h2 class='custom-heading'>Subadmin Panel</h2>", unsafe_allow_html=True)

    st.subheader("👥 View Users")
    users_df = pd.DataFrame(list(users_col.find({}, {"_id": 0, "email": 1, "role": 1})))
    st.dataframe(users_df)

    st.subheader("➕ Add / Manage Tasks")
    user_emails = [u["email"] for u in users_col.find({"role": "user"}, {"email": 1})]

    with st.expander("Add New Task"):
        with st.form("add_task_subadmin"):
            assigned_to = st.selectbox("Assign To", user_emails)
            project_name = st.text_input("Project Name")
            expected_hours = st.number_input("Expected Hours", min_value=0.0)
            status = st.selectbox("Status", ["Started", "Progressing", "Completed", "Incomplete"])
            department = st.selectbox("Department", ["Sales","Accounts","HR","Marketing","IT"])
            remark = st.selectbox("Remark", ["Green Flag", "Red Flag"])
            submitted = st.form_submit_button("Add Task")
            if submitted:
                if not project_name.strip():
                    st.error("Project Name required")
                else:
                    tasks_col.insert_one({
                        "assigned_to": assigned_to,
                        "project_name": project_name,
                        "expected_hours": expected_hours,
                        "status": status,
                        "department": department,
                        "remark": remark,
                        "message": ""
                    })
                    st.success(f"Task for {project_name} assigned to {assigned_to}")

    tasks_df = get_tasks()
    st.dataframe(tasks_df)

# ---------- USER PANEL ----------
def user_panel(user_email):
    st.markdown("<h2 class='custom-heading'>User Panel</h2>", unsafe_allow_html=True)
    st.subheader("My Tasks")

    tasks_df = get_tasks(user_email)
    if tasks_df.empty:
        st.warning("No tasks assigned.")
        return

    st.write("### 📅 Daily Task Logs with Totals")
    st.dataframe(tasks_df, use_container_width=True)

    st.subheader("Update Task Status / Add Hours / Message")
    unique_tasks = tasks_df.drop_duplicates(subset=["_id"])
    selected_task_id = st.selectbox("Select Task", unique_tasks["_id"].tolist())
    selected_task = tasks_col.find_one({"_id": ObjectId(selected_task_id)})

    new_status = st.selectbox("Update Status",
                              ["Started", "Progressing", "Completed", "Incomplete"],
                              index=["Started","Progressing","Completed","Incomplete"].index(selected_task["status"]))
    hours_today = st.number_input("Hours worked today", min_value=0.0, step=0.5)
    new_message = st.text_area("Message (optional, max 100 chars)",
                               value=selected_task.get("message", ""),
                               max_chars=100)

    if st.button("Submit Update", key="submit_update_btn"):
        tasks_col.update_one({"_id": ObjectId(selected_task_id)}, {"$set": {"status": new_status, "message": new_message}})
        if hours_today > 0:
            task_hours_col.insert_one({
                "task_id": ObjectId(selected_task_id),
                "user_email": user_email,
                "hours_spent": hours_today,
                "log_date": datetime.date.today()
            })
        st.success(f"Task updated! {hours_today} hours added.")
        st.rerun()

# ---------- MAIN APP ----------
def main():
    st.markdown("<h2 class='custom-heading'>Project Management App</h2>", unsafe_allow_html=True)


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

        if st.button("Logout"):
            st.session_state["logged_in"] = False
            st.rerun()

        if st.session_state["role"] == "admin":
            admin_panel()
        elif st.session_state["role"] == "subadmin":
            subadmin_panel(st.session_state["email"])
        else:
            user_panel(st.session_state["email"])

if __name__=="__main__":
    main()
