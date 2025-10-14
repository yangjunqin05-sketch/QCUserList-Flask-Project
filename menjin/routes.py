# menjin/routes.py (已修正)

# 关键修正 1: 从 flask 导入 jsonify
from flask import request, render_template, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
# from app import db
# from app.models import MenjinDeletionRequest
import pyodbc
import time
import json
from . import bp
from . import db_config

ADMIN_EXECUTION_PASSWORD = "execute_password123"

# --- 数据库连接和辅助函数 ---
def get_db_connection():
    try:
        conn = pyodbc.connect(db_config.DB_CONNECTION_STRING, autocommit=False)
        return conn
    except pyodbc.Error as ex:
        print_log(f"数据库连接错误: {ex.args[0]}", "ERROR")
        return None

def print_log(message, level="INFO"):
    print(f"[{level}] {time.strftime('%Y-%m-%d %H:%M:%S')} - {message}")

def execute_stored_procedure(sp_name, params=(), conn_to_use=None):
    is_external_conn = conn_to_use is not None
    conn = conn_to_use if is_external_conn else get_db_connection()
    if not conn: return [], -999, "数据库连接失败"
    cursor = None; data_to_return = [[]]; ret_code_from_sp = -1; db_error_msg = None
    try:
        cursor = conn.cursor()
        param_placeholders = ', '.join(['?'] * len(params))
        sql_query = f"SET NOCOUNT ON; DECLARE @return_status INT; EXEC @return_status = {sp_name} {param_placeholders}; SELECT @return_status AS ReturnValue;"
        cursor.execute(sql_query, params)
        results_data_sets = []
        while cursor.description is not None:
            rows = cursor.fetchall()
            current_results_list = [dict(zip([col[0] for col in cursor.description], row)) for row in rows] if rows else []
            results_data_sets.append(current_results_list)
            if not cursor.nextset(): break
        if results_data_sets and results_data_sets[-1] and isinstance(results_data_sets[-1], list) and len(results_data_sets[-1]) > 0:
            last_potential_ret_set = results_data_sets[-1]
            if isinstance(last_potential_ret_set[0], dict) and 'ReturnValue' in last_potential_ret_set[0]:
                ret_code_from_sp = last_potential_ret_set[0]['ReturnValue']
                data_to_return = results_data_sets[:-1]
            else:
                data_to_return = results_data_sets
                if not db_error_msg: ret_code_from_sp = 0 
        elif not results_data_sets and cursor.rowcount != -1:
            if sp_name == 'sp_wg2014_ConsumerDelete' and db_error_msg is None: ret_code_from_sp = 0
        if not is_external_conn: conn.commit()
    except pyodbc.Error as ex:
        if not is_external_conn and conn: conn.rollback()
        db_error_msg = f"数据库操作失败: {str(ex)}"
        ret_code_from_sp = -1
        print_log(f"执行SP {sp_name} 错误: {str(ex)} (SQLState: {ex.args[0]})", "ERROR")
    finally:
        if cursor: cursor.close()
        if not is_external_conn and conn: conn.close()
    if not isinstance(data_to_return, list) or not all(isinstance(ds, list) for ds in data_to_return):
         data_to_return = [data_to_return] if isinstance(data_to_return, list) and len(data_to_return) > 0 and isinstance(data_to_return[0], dict) else [[]]
    final_data = data_to_return[0] if len(data_to_return) == 1 else data_to_return
    return final_data, ret_code_from_sp, db_error_msg

def get_sp_error_message(ret_code):
    error_map = {0:"成功执行。",101:"工号不能为空。",102:"工号已被使用。",103:"工号不存在。",201:"用户姓名不能为空。",301:"卡号不能为空。",302:"卡号已被使用。",303:"卡号必须大于100, 小于 4294967295。",304:"用户已有卡号。",305:"用户没有卡号。",401:"部门班组名必须是已存在的。",501:"门名称或楼层名称 不能为空。",502:"门名称或楼层名称 不存在。",601:"时段索引号必须小于254。",602:"权限类型不存在。",701:"部门名称不能为空。",702:"部门已被使用。",703:"上级部门不存在。",704:"指定部门不存在。",9:"SQL Server 错误。",-1:"数据库操作失败 (内部错误)。",-999:"数据库连接失败。"}
    return error_map.get(ret_code, f"未知存储过程返回代码: {ret_code}")

def _get_filtered_users(conn, search_name, department_id_str):
    """
    Fetches a filtered list of users from the database.
    Now includes the DepartmentID for each user.
    """
    users = []
    try:
        with conn.cursor() as cursor:
            # CORE CHANGE 1: Add c.f_GroupID AS DepartmentID to the SELECT statement
            user_query = """
                SELECT c.f_ConsumerID, c.f_ConsumerNO, c.f_ConsumerName, c.f_CardNO, 
                       c.f_GroupID AS DepartmentID,
                       g.f_GroupName AS DepartmentName, 
                       pt.f_PrivilegeTypeName AS PrivilegeType 
                FROM t_b_Consumer c 
                LEFT JOIN t_b_Group g ON c.f_GroupID = g.f_GroupID 
                LEFT JOIN t_d_PrivilegeType pt ON c.f_PrivilegeTypeID = pt.f_PrivilegeTypeID
            """
            # ... (the rest of this function remains unchanged) ...
            conditions, params = [], []
            if search_name: 
                conditions.append("c.f_ConsumerName LIKE ?")
                params.append(f"%{search_name}%")
            if department_id_str:
                try: 
                    conditions.append("c.f_GroupID = ?")
                    params.append(int(department_id_str))
                except ValueError: 
                    pass
            if conditions: 
                user_query += " WHERE " + " AND ".join(conditions)
            user_query += " ORDER BY c.f_ConsumerNO ASC;"
            cursor.execute(user_query, tuple(params))
            if cursor.description:
                users = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
    except pyodbc.Error as ex:
        print_log(f"Error fetching filtered users: {ex}", "ERROR")
    return users

def _update_user_department_in_db(consumer_no, new_department_id):
    """
    Directly updates the department for a given user.
    Returns True on success, False on failure.
    """
    conn = get_db_connection()
    if not conn:
        return False
    
    # If the new_department_id is an empty string, we should set it to NULL
    dept_id_to_set = new_department_id if new_department_id is not None else None

    sql = "UPDATE t_b_Consumer SET f_GroupID = ? WHERE f_ConsumerNO = ?"
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (dept_id_to_set, consumer_no))
        conn.commit()
        return True
    except pyodbc.Error as ex:
        conn.rollback()
        print_log(f"Failed to update department for user {consumer_no}: {ex}", "ERROR")
        return False
    finally:
        if conn:
            conn.close()

@bp.route('/users/<string:consumer_no>/update_department', methods=['POST'])
@login_required
def update_department(consumer_no):
    new_department_id_str = request.form.get('department_id')
    
    # Convert empty string to None, otherwise convert to int
    new_department_id = None
    if new_department_id_str and new_department_id_str.isdigit():
        new_department_id = int(new_department_id_str)
    elif new_department_id_str: # If it's not empty and not a digit, it's an error
        flash("无效的部门ID。", "danger")
        return redirect(url_for('menjin.list_users_page'))

    # Get user details for the flash message
    user_details = get_user_details_by_no(consumer_no)
    user_name = user_details.get('f_ConsumerName', consumer_no) if user_details else consumer_no

    if _update_user_department_in_db(consumer_no, new_department_id):
        flash(f"用户 “{user_name}” 的部门已成功更新。", "success")
    else:
        flash(f"更新用户 “{user_name}” 的部门失败，请检查日志或联系管理员。", "danger")

    return redirect(url_for('menjin.list_users_page'))

def get_user_details_by_no(consumer_no, conn_to_use=None):
    is_external_conn = conn_to_use is not None; conn = conn_to_use if is_external_conn else get_db_connection()
    if not conn: return None
    cursor = None; user_data = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT f_ConsumerID, f_ConsumerNO, f_ConsumerName, f_GroupID FROM t_b_Consumer WHERE f_ConsumerNO = ?", (consumer_no,))
        row = cursor.fetchone()
        if row and cursor.description: user_data = dict(zip([col[0] for col in cursor.description], row))
    except pyodbc.Error as ex: print_log(f"get_user_details_by_no 错误 for {consumer_no}: {ex}", "ERROR")
    finally:
        if cursor: cursor.close()
        if not is_external_conn and conn: conn.close()
    return user_data

# 关键修正 2: 删除了这里重复的 get_user_details_by_no 函数

def get_user_details_by_id(consumer_id, conn_to_use=None):
    is_external_conn = conn_to_use is not None; conn = conn_to_use if is_external_conn else get_db_connection()
    if not conn: return None
    cursor = None; user_data = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT f_ConsumerID, f_ConsumerNO, f_ConsumerName, f_GroupID FROM t_b_Consumer WHERE f_ConsumerID = ?", (consumer_id,))
        row = cursor.fetchone()
        if row and cursor.description: user_data = dict(zip([col[0] for col in cursor.description], row))
    except pyodbc.Error as ex: print_log(f"get_user_details_by_id 错误 for {consumer_id}: {ex}", "ERROR")
    finally:
        if cursor: cursor.close()
        if not is_external_conn and conn: conn.close()
    return user_data

def get_door_details_by_id(door_id, conn_to_use=None):
    is_external_conn = conn_to_use is not None; conn = conn_to_use if is_external_conn else get_db_connection()
    if not conn: return None
    cursor = None; door_data = None
    try:
        cursor = conn.cursor()
        sql = "SELECT d.f_DoorID, d.f_DoorName, c.f_ControllerID, cz.f_ZoneID, cz.f_ZoneName FROM t_b_Door d JOIN t_b_Controller c ON d.f_ControllerID = c.f_ControllerID LEFT JOIN t_b_Controller_Zone cz ON c.f_ZoneID = cz.f_ZoneID WHERE d.f_DoorID = ?"
        cursor.execute(sql, (door_id,))
        row = cursor.fetchone()
        if row and cursor.description: door_data = dict(zip([col[0] for col in cursor.description], row))
    except pyodbc.Error as ex: print_log(f"get_door_details_by_id 错误 for {door_id}: {ex}", "ERROR")
    finally:
        if cursor: cursor.close()
        if not is_external_conn and conn: conn.close()
    return door_data

def get_control_seg_details_by_id(control_seg_id, conn_to_use=None):
    is_external_conn = conn_to_use is not None; conn = conn_to_use if is_external_conn else get_db_connection()
    if not conn: return None
    cursor = None; seg_data = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT f_ControlSegID, f_ControlSegName FROM t_b_ControlSeg WHERE f_ControlSegID = ?", (control_seg_id,))
        row = cursor.fetchone()
        if row and cursor.description: seg_data = dict(zip([col[0] for col in cursor.description], row))
    except pyodbc.Error as ex: print_log(f"get_control_seg_details_by_id 错误 for {control_seg_id}: {ex}", "ERROR")
    finally:
        if cursor: cursor.close()
        if not is_external_conn and conn: conn.close()
    return seg_data
    

def add_pending_action(action_type, **kwargs):
    conn = get_db_connection()
    if not conn: print_log(f"添加待处理操作失败: 数据库连接失败", "ERROR"); return False
    details = {k: v for k, v in kwargs.items() if v is not None}
    user_display = details.get('target_user_name') or details.get('target_user_no') or f"ID:{details.get('target_consumer_id')}"
    if action_type == "DELETE_USER":
        details['description'] = f"请求删除用户: {user_display}"
    elif action_type == "DELETE_PRIVILEGE":
        door_display = details.get('target_door_name') or f"ID:{details.get('target_door_id')}"
        if details.get('target_door_zone_name'): door_display += f" (区域: {details.get('target_door_zone_name')})"
        seg_display = details.get('target_control_seg_name', "全时段") if details.get('target_control_seg_id', 1) != 0 else "未指定时段"
        details['description'] = f"请求删除权限: 用户 '{user_display}' 对门 '{door_display}' (时段: {seg_display})"
    sql = "INSERT INTO t_PendingActions (f_ActionType, f_TargetUserNO, f_TargetDoorID, f_TargetControlSegID, f_ActionDetails, f_Status) VALUES (?, ?, ?, ?, ?, 'Pending')"
    try:
        with conn.cursor() as cursor:
            details_json = json.dumps(details, ensure_ascii=False)
            cursor.execute(sql, (action_type, details.get('target_user_no'), details.get('target_door_id'), details.get('target_control_seg_id'), details_json))
        conn.commit()
        return True
    except pyodbc.Error as ex:
        conn.rollback(); print_log(f"添加待处理操作失败: {ex}", "ERROR"); return False
    finally:
        if conn: conn.close()

def get_pending_actions_from_db():
    actions = []; conn = get_db_connection()
    if not conn: return actions
    sql = "SELECT f_ActionID, f_ActionType, f_Timestamp, f_ActionDetails FROM t_PendingActions WHERE f_Status = 'Pending' ORDER BY f_Timestamp DESC"
    try:
        with conn.cursor() as cursor:
            rows = cursor.execute(sql).fetchall()
            if rows:
                columns = [col[0] for col in cursor.description]
                for row in rows:
                    action = dict(zip(columns, row))
                    try: action['f_ActionDetails_parsed'] = json.loads(action['f_ActionDetails'])
                    except (json.JSONDecodeError, TypeError): action['f_ActionDetails_parsed'] = {"description": "无法解析"}
                    actions.append(action)
    except pyodbc.Error as ex: print_log(f"获取待处理操作列表失败: {ex}", "ERROR")
    finally:
        if conn: conn.close()
    return actions

def cancel_pending_action_in_db(action_id):
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE t_PendingActions SET f_Status = 'Cancelled' WHERE f_ActionID = ? AND f_Status = 'Pending'", (action_id,))
        conn.commit(); return cursor.rowcount > 0
    except pyodbc.Error as ex:
        conn.rollback(); print_log(f"撤销待处理操作 {action_id} 失败: {ex}", "ERROR"); return False
    finally:
        if conn: conn.close()

# --- 网页路由 ---
@bp.route('/')
@login_required # <-- 应用登录保护
def index_page(): 
    return redirect(url_for('menjin.list_users_page'))


@bp.route('/users', methods=['GET'])
@login_required # <-- 应用登录保护
def list_users_page():
    conn = get_db_connection()
    departments = []
    initial_users = []
    if not conn: 
        flash("数据库连接失败。", "error")
    else:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT f_GroupID, f_GroupName FROM t_b_Group ORDER BY f_GroupName;")
                departments = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
            initial_users = _get_filtered_users(conn, '', '')
        except pyodbc.Error as ex:
            print_log(f"加载用户页面错误: {ex}", "ERROR")
            flash(f"查询部门列表失败: {str(ex)}", "error")
        finally:
            if conn: conn.close()
    return render_template('users_list_simple.html', 
                           users=initial_users, 
                           departments=departments, 
                           title="用户查询")




@bp.route('/api/users', methods=['GET'])
@login_required 
def api_get_users():
    search_name = request.args.get('search_name', '').strip()
    department_id_str = request.args.get('department_id', '').strip()
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "数据库连接失败"}), 500
    try:
        users = _get_filtered_users(conn, search_name, department_id_str)
        return jsonify(users)
    finally:
        if conn: conn.close()

@bp.route('/users/add', methods=['GET', 'POST'])
def add_user_page():
    if request.method == 'POST':
        form_data = {k: v.strip() for k, v in request.form.items()}
        consumer_no, consumer_name = form_data.get('consumerNO'), form_data.get('consumerName')
        if not consumer_no or not consumer_name:
            flash("工号和姓名不能为空。", "error"); return render_template('add_user.html', title="添加用户", **form_data)
        card_no = int(form_data.get('cardNO')) if form_data.get('cardNO', '').isdigit() else 0
        _, ret_code, db_error = execute_stored_procedure('sp_wg_Consumer_add', (consumer_no, consumer_name, card_no, form_data.get('departmentName', '')))
        if ret_code == 0:
            flash(f"用户 '{consumer_name}' 添加成功！", "success"); return redirect(url_for('menjin.list_users_page'))
        else:
            flash(f"添加失败: {get_sp_error_message(ret_code)} {db_error or ''}", "error"); return render_template('add_user.html', title="添加用户", **form_data)
    return render_template('add_user.html', title="添加用户")

@bp.route('/users/<string:consumer_no>/delete/request', methods=['POST'])
@login_required
def request_delete_user(consumer_no):
    from app import db
    from app.models import MenjinDeletionRequest
    user_details = get_user_details_by_no(consumer_no)
    if not user_details:
        flash(f"工号为 '{consumer_no}' 的门禁用户不存在。", "warning")
        return redirect(url_for('menjin.list_users_page'))

    # 检查是否已有待处理的申请
    existing_request = MenjinDeletionRequest.query.filter_by(
        consumer_no=consumer_no, 
        status='pending'
    ).first()
    if existing_request:
        flash(f"删除门禁用户 '{user_details.get('f_ConsumerName')}' 的申请已存在，请等待管理员处理。", "info")
        return redirect(url_for('menjin.list_users_page'))

    # --- 使用 try...except 块来确保数据库写入的原子性和错误捕获 ---
    try:
        new_req = MenjinDeletionRequest(
            requested_by_id=current_user.id,
            consumer_no=consumer_no,
            consumer_name=user_details.get('f_ConsumerName', '未知姓名')
        )
        db.session.add(new_req)
        db.session.commit() # 尝试提交
        
        # 只有在 commit 成功后才 flash 成功消息
        flash(f"删除门禁用户 '{user_details.get('f_ConsumerName')}' 的申请已成功提交。", "success")
    
    except Exception as e:
        db.session.rollback() # 如果失败，必须回滚，防止数据库会话出错
        # 在服务器后台打印详细错误，这是我们调试的关键！
        print_log(f"!!! 写入 MenjinDeletionRequest 到 app.db 失败: {e}", "ERROR")
        # 给用户一个友好的错误提示
        flash("提交申请失败，发生内部错误，请联系管理员。", "danger")

    return redirect(url_for('menjin.list_users_page'))

@bp.route('/privileges', methods=['GET'])
@login_required 
def privileges_query_page():
    query_type = request.args.get('query_type', 'user')
    target_consumer_id_str = request.args.get('target_consumer_id', '').strip()
    target_door_id_str = request.args.get('target_door_id', '').strip()
    filter_user_department_id_str = request.args.get('filter_user_department', '').strip()
    filter_department_id_for_door_query_str = request.args.get('filter_department_id_for_door_query', '').strip()
    filter_zone_id_for_door_query_str = request.args.get('filter_zone_id_for_door_query', '').strip()
    users_for_select, doors_for_select, departments_for_select, zones_for_select = [], [], [], []
    query_results, query_target_display_name = [], None
    conn = get_db_connection()
    if not conn: 
        flash("数据库连接失败。", "error")
    else:
        try:
            with conn.cursor() as cursor:
                user_select_sql = "SELECT f_ConsumerID, f_ConsumerNO, f_ConsumerName FROM t_b_Consumer"
                user_params = []
                if query_type == 'user' and filter_user_department_id_str:
                    try:
                        user_select_sql += " WHERE f_GroupID = ?"
                        user_params.append(int(filter_user_department_id_str))
                    except ValueError:
                        flash("筛选用户部门ID无效，将显示所有用户。", "warning")
                user_select_sql += " ORDER BY f_ConsumerName"
                cursor.execute(user_select_sql, tuple(user_params))
                if cursor.description: 
                    users_for_select = [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]
                door_select_sql = "SELECT d.f_DoorID, d.f_DoorName FROM t_b_Door d LEFT JOIN t_b_Controller c ON d.f_ControllerID = c.f_ControllerID"
                door_params = []
                if query_type == 'door' and filter_zone_id_for_door_query_str:
                    try:
                        door_select_sql += " WHERE c.f_ZoneID = ?"
                        door_params.append(int(filter_zone_id_for_door_query_str))
                    except ValueError:
                        flash("筛选门区域ID无效，将显示所有门。", "warning")
                door_select_sql += " ORDER BY d.f_DoorName"
                cursor.execute(door_select_sql, tuple(door_params))
                if cursor.description: 
                    doors_for_select = [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]
                cursor.execute("SELECT f_GroupID, f_GroupName FROM t_b_Group ORDER BY f_GroupName", ())
                if cursor.description: 
                    departments_for_select = [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]
                cursor.execute("SELECT f_ZoneID, f_ZoneName FROM t_b_Controller_Zone ORDER BY f_ZoneName", ())
                if cursor.description: 
                    zones_for_select = [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]
                if query_type == 'user' and target_consumer_id_str:
                    try:
                        target_consumer_id = int(target_consumer_id_str)
                        selected_user_details = get_user_details_by_id(target_consumer_id, conn_to_use=conn)
                        if selected_user_details:
                            query_target_display_name = f"用户: {selected_user_details['f_ConsumerName']} ({selected_user_details['f_ConsumerNO']})"
                            sql = """
                                SELECT u.f_ConsumerID, u.f_ConsumerNO, u.f_ConsumerName, 
                                       d.f_DoorName AS DoorName, p.f_DoorID AS DoorID, 
                                       cz.f_ZoneName as ZoneName,
                                       cs.f_ControlSegName AS ControlSegName, p.f_ControlSegID AS ControlSegID
                                FROM t_d_Privilege p
                                JOIN t_b_Consumer u ON p.f_ConsumerID = u.f_ConsumerID 
                                JOIN t_b_Door d ON p.f_DoorID = d.f_DoorID
                                LEFT JOIN t_b_Controller c ON d.f_ControllerID = c.f_ControllerID
                                LEFT JOIN t_b_Controller_Zone cz ON c.f_ZoneID = cz.f_ZoneID
                                LEFT JOIN t_b_ControlSeg cs ON p.f_ControlSegID = cs.f_ControlSegID
                                WHERE p.f_ConsumerID = ? ORDER BY d.f_DoorName;
                            """
                            cursor.execute(sql, (target_consumer_id,))
                            if cursor.description: query_results = [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]
                        else: flash(f"未找到ID为 '{target_consumer_id_str}' 的用户。", "warning")
                    except ValueError: flash("用户ID必须是数字。", "error")
                elif query_type == 'door' and target_door_id_str:
                    try:
                        target_door_id = int(target_door_id_str)
                        door_details = get_door_details_by_id(target_door_id, conn_to_use=conn)
                        if door_details:
                            query_target_display_name = f"门: {door_details['f_DoorName']}"
                            if door_details.get('f_ZoneName'): query_target_display_name += f" (区域: {door_details['f_ZoneName']})"
                            sql = """
                                SELECT u.f_ConsumerID, u.f_ConsumerNO, u.f_ConsumerName, g.f_GroupName AS DepartmentName,
                                       cs.f_ControlSegName AS ControlSegName, p.f_ControlSegID AS ControlSegID, p.f_DoorID AS DoorID
                                FROM t_d_Privilege p
                                JOIN t_b_Consumer u ON p.f_ConsumerID = u.f_ConsumerID
                                LEFT JOIN t_b_Group g ON u.f_GroupID = g.f_GroupID
                                LEFT JOIN t_b_ControlSeg cs ON p.f_ControlSegID = cs.f_ControlSegID
                                WHERE p.f_DoorID = ?
                            """
                            params_q = [target_door_id]
                            if filter_department_id_for_door_query_str:
                                try:
                                    sql += " AND u.f_GroupID = ?"; params_q.append(int(filter_department_id_for_door_query_str))
                                except ValueError: flash("筛选用户部门ID无效。", "warning")
                            sql += " ORDER BY u.f_ConsumerName;"
                            cursor.execute(sql, tuple(params_q))
                            if cursor.description: query_results = [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]
                        else: flash(f"未找到ID为 '{target_door_id_str}' 的门。", "warning")
                    except ValueError: flash("门ID必须是数字。", "error")
        except pyodbc.Error as ex:
            print_log(f"权限查询页面错误: {ex}", "ERROR"); flash(f"查询权限失败: {ex}", "error")
        finally:
            if conn: conn.close()
    return render_template('privileges_query.html',
                           query_type=query_type, 
                           users_for_select=users_for_select,
                           doors_for_select=doors_for_select, 
                           departments_for_select=departments_for_select,
                           zones_for_select=zones_for_select, 
                           query_results=query_results,
                           query_target_display_name=query_target_display_name,
                           selected_consumer_id=target_consumer_id_str, 
                           selected_door_id=target_door_id_str,
                           selected_user_department_filter=filter_user_department_id_str,
                           selected_department_id_for_door_query=filter_department_id_for_door_query_str,
                           selected_zone_id_for_door_query=filter_zone_id_for_door_query_str,
                           title="权限查询")

@bp.route('/privileges/delete/request', methods=['POST'])
def request_delete_specific_privilege():
    form = request.form
    try:
        consumer_id = int(form['consumer_id_to_delete_priv'])
        door_id = int(form['door_id_to_delete_priv'])
        control_seg_id = int(form['control_seg_id_to_delete_priv'])
    except (ValueError, KeyError):
        flash("提交的ID无效。", "error")
    else:
        user_details = get_user_details_by_id(consumer_id)
        door_details = get_door_details_by_id(door_id)
        seg_details = get_control_seg_details_by_id(control_seg_id)
        details_for_action = {
            "target_consumer_id": consumer_id, "target_user_no": user_details.get('f_ConsumerNO'), "target_user_name": user_details.get('f_ConsumerName'),
            "target_door_id": door_id, "target_door_name": door_details.get('f_DoorName'), "target_door_zone_name": door_details.get('f_ZoneName'),
            "target_control_seg_id": control_seg_id, "target_control_seg_name": seg_details.get('f_ControlSegName')
        }
        if add_pending_action(action_type="DELETE_PRIVILEGE", **details_for_action):
            flash("删除权限请求已提交。", "success")
        else: flash("提交删除权限请求失败。", "error")
    redirect_args = {k.replace('_for_redirect', '').replace('current_', ''): v for k, v in form.items() if k.startswith('current_')}
    return redirect(url_for('menjin.privileges_query_page', **redirect_args))
