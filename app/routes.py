# app/routes.py
from flask import render_template, flash, redirect, url_for, request, Blueprint, jsonify
from flask_login import current_user, login_user, logout_user, login_required
from app import db
from app.models import (User, System, SystemAccount, CheckHistory, SystemUser, WorkstationUser, 
                        SystemRole, DisableRequest, Group, Script, Job, UserRequest,RoleChangeRequest,
                        MenjinDeletionRequest, PartialDisableRequest)
from app.forms import (LoginForm, SearchUserForm, EditSystemForm, AssignGroupForm, 
                       AddSystemForm, GroupForm, ScriptForm, ExecuteJobForm,
                       UserRequestForm, AdminUserForm, AddComputerUserForm, 
                       AddWorkstationUserForm, BatchImportForm,RoleChangeRequestForm)
from datetime import date, timedelta, datetime
from functools import wraps
from sqlalchemy import or_
from flask import session
from collections import defaultdict
import json


bp = Blueprint('routes', __name__)

@bp.before_request
def before_request():
    session.permanent = True
    session.modified = True

# --- 辅助函数 ---
def populate_group_choices(form):
    """
    一个辅助函数，用于从数据库动态填充表单的分组选项。
    """
    # 检查表单中是否有 'group' 字段
    if hasattr(form, 'group'):
        groups = Group.query.order_by(Group.name).all()
        # coerce=int 后, '未分组' 选项的 value 应该是 '0' (一个可以被 int() 处理但又不是真实ID的值)
        form.group.choices = [(0, '未分组')] + [(g.id, g.name) for g in groups]
# --- 装饰器 ---
def roles_required(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                flash('您没有权限访问此页面。', 'danger')
                return redirect(url_for('routes.index'))
            return f(*args, **kwargs)
        return decorated_function
    return wrapper
# --- 核心用户界面路由 ---

@bp.route('/')
@bp.route('/index')
@login_required
def index():
    group_filter_id = request.args.get('group', 0, type=int)
    query = System.query
    if group_filter_id != 0:
        query = query.filter(System.group_id == group_filter_id)
    systems = query.order_by(System.system_number.asc()).all()
    all_groups = Group.query.order_by(Group.id).all()
    
    return render_template('index_overview.html', title='系统概览', 
                           systems=systems, all_groups=all_groups, 
                           current_group_id=group_filter_id)


@bp.route('/it_check_manage')
@login_required
@roles_required('admin')
def it_check_manage():
    # --- 确保所有需要的变量都已定义 ---
    group_filter_id = request.args.get('group', 0, type=int)
    sort_by = request.args.get('sort_by', 'default')
    
    query = System.query
    if group_filter_id != 0:
        query = query.filter(System.group_id == group_filter_id)
        
    if sort_by == 'next_check_date':
        query = query.order_by(System.next_check_date.asc())
    else:
        query = query.order_by(System.system_number.asc())
        
    systems = query.all()
    today = date.today() # <--- 之前可能遗漏了这行
    all_groups = Group.query.order_by(Group.id).all() # <--- 这行是关键
    
    add_form = AddSystemForm()
    # 动态填充分组选项
    if hasattr(add_form, 'group'):
        # 注意：这里需要重新查询一次 groups，因为 all_groups 是给筛选框用的
        groups = Group.query.order_by(Group.name).all()
        add_form.group.choices = [(0, '未分组')] + [(g.id, g.name) for g in groups]
        
    # --- 核心修正：确保所有变量都被传递给模板 ---
    return render_template('it_check_manage.html', 
                           title='IT核查管理', 
                           systems=systems, 
                           today=today,
                           add_system_form=add_form, 
                           all_groups=all_groups, 
                           current_group_id=group_filter_id, 
                           sort_by=sort_by)

@bp.route('/system/<int:system_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'qc')
def system_detail(system_id):
    system = System.query.get_or_404(system_id)
    scripts = Script.query.order_by(Script.name).all()
    form_computer = AddComputerUserForm() if current_user.role == 'admin' else None
    form_workstation = AddWorkstationUserForm() if current_user.role == 'admin' else None
    execute_form = None
    if current_user.role == 'admin':
        execute_form = ExecuteJobForm()
        execute_form.script.choices = [(s.id, s.name) for s in Script.query.order_by(Script.name).all()]
    if current_user.role == 'admin' and request.method == 'POST':
        # --- 电脑用户处理逻辑 ---
        if 'submit_computer' in request.form and form_computer.validate_on_submit():
            username = form_computer.username.data.strip()
            # 严格唯一性检查：检查该 username 是否已作为电脑用户存在于当前系统
            existing_account_id = db.session.query(SystemAccount.id).filter(SystemAccount.username.ilike(username)).scalar()
            if existing_account_id and SystemUser.query.filter_by(account_id=existing_account_id, system_id=system.id).first():
                flash(f'添加失败：电脑用户 “{username}” 已存在于该系统中。', 'danger')
            else:
                account = find_or_create_system_account(username, form_computer.chinese_name.data)
                db.session.add(SystemUser(system_id=system.id, account_id=account.id, system_role=form_computer.system_role.data.strip()))
                db.session.commit()
                flash('电脑用户已成功添加。', 'success')
            return redirect(url_for('routes.system_detail', system_id=system.id))

        # --- 工作站用户处理逻辑 ---
        if 'submit_workstation' in request.form and form_workstation.validate_on_submit():
            username = form_workstation.username.data.strip()
            # 严格唯一性检查：检查该 username 是否已作为工作站用户存在于当前系统
            existing_account_id = db.session.query(SystemAccount.id).filter(SystemAccount.username.ilike(username)).scalar()
            if existing_account_id and WorkstationUser.query.filter_by(account_id=existing_account_id, system_id=system.id).first():
                 flash(f'添加失败：工作站用户 “{username}” 已存在于该系统中。', 'danger')
            else:
                account = find_or_create_system_account(username, form_workstation.chinese_name.data)
                role_name = form_workstation.role.data.strip()
                role = SystemRole.query.filter_by(name=role_name).first() or SystemRole(name=role_name)
                db.session.add(role)
                db.session.add(WorkstationUser(system_id=system.id, account_id=account.id, role=role))
                db.session.commit()
                flash('工作站用户已成功添加。', 'success')
            return redirect(url_for('routes.system_detail', system_id=system.id))

    return render_template('system_detail.html', title=system.name, system=system, scripts=scripts,
                           add_sys_user_form=form_computer, add_ws_user_form=form_workstation,execute_form=execute_form)

@bp.route('/system/enable_user_link/<link_type>/<int:link_id>', methods=['POST'])
@login_required
@roles_required('admin')
def enable_user_link(link_type, link_id):
    Model = SystemUser if link_type == 'computer' else WorkstationUser
    link = Model.query.get_or_404(link_id)
    link.is_active = True
    db.session.commit()
    flash(f"用户 “{link.account.chinese_name}” 在系统 “{link.system.name}” 中的权限已重新启用。", "success")
    return redirect(url_for('routes.system_detail', system_id=link.system_id))



@bp.route('/system/<int:system_id>/batch_import', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def batch_import_users(system_id):
    system = System.query.get_or_404(system_id)
    form = BatchImportForm()
    
    if form.validate_on_submit():
        user_data = form.user_data.data
        import_type = form.import_type.data
        lines = user_data.strip().split('\n')
        
        processed_count = 0
        skipped_list = [] # 用于记录被跳过的行
        
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line: continue
            
            parts = [p.strip() for p in line.split(',')]
            if len(parts) != 3:
                skipped_list.append(f"第 {i} 行: 格式错误 (应为3列)")
                continue

            username, chinese_name, role_name = parts
            
            # 使用“找到或创建”的辅助函数
            account = find_or_create_system_account(username, chinese_name)
            
            # --- 核心修正：增加对 account 是否为 None 的检查 ---
            if not account:
                skipped_list.append(f"第 {i} 行: 用户名为空，已跳过。")
                continue # 跳到下一行

            # 检查重复权限
            if import_type == 'computer':
                if not SystemUser.query.filter_by(account_id=account.id, system_id=system.id, system_role=role_name).first():
                    db.session.add(SystemUser(system_id=system.id, account_id=account.id, system_role=role_name))
            elif import_type == 'workstation':
                role = SystemRole.query.filter(SystemRole.name.ilike(role_name)).first()
                if not role:
                    role = SystemRole(name=role_name)
                    db.session.add(role)
                    db.session.flush()
                if not WorkstationUser.query.filter_by(account_id=account.id, system_id=system.id, role_id=role.id).first():
                    db.session.add(WorkstationUser(system_id=system.id, account_id=account.id, role_id=role.id))
            
            processed_count += 1
        
        db.session.commit()
        flash(f'批量处理完成！共处理 {processed_count} 条有效记录。', 'success')
        if skipped_list:
            flash('以下记录因格式错误或信息不全而被跳过：\n' + '\n'.join(skipped_list), 'warning')

        return redirect(url_for('routes.system_detail', system_id=system.id))

    return render_template('batch_import.html', title='批量导入用户', system=system, form=form)

@bp.route('/backup_dashboard')
@login_required
@roles_required('admin', 'qc')
def backup_dashboard():
    systems = System.query.order_by(System.system_number).all()
    return render_template('backup_dashboard.html', title='系统备份清单', systems=systems)

@bp.route('/restore_dashboard')
@login_required
@roles_required('admin', 'qc')
def restore_dashboard():
    systems = System.query.order_by(System.system_number).all()
    return render_template('restore_verification_dashboard.html', title='备份还原验证清单', 
                           systems=systems, today=date.today())

@bp.route('/qa_dashboard')
@login_required
@roles_required('admin', 'qa')
def qa_dashboard():
    """QA 核查列表页面 - 增加智能排序和“是否核查”开关"""
    group_filter_id = request.args.get('group', 0, type=int)
    sort_by = request.args.get('sort_by', 'default')

    query = System.query
    if group_filter_id != 0:
        query = query.filter(System.group_id == group_filter_id)
    
    # 核心修改：双重排序
    # 1. 首先按 needs_qa_check 降序 (True, 即需要核查的, 排在前面)
    # 2. 然后再按用户选择的排序方式
    if sort_by == 'qa_next_check_date':
        query = query.order_by(System.needs_qa_check.desc(), System.qa_next_check_date.asc())
    else:
        query = query.order_by(System.needs_qa_check.desc(), System.system_number.asc())

    systems = query.all()
    all_groups = Group.query.order_by(Group.id).all()

    return render_template('qa_dashboard.html', title='QA 核查列表', 
                           systems=systems, today=date.today(),
                           all_groups=all_groups, current_group_id=group_filter_id, 
                           sort_by=sort_by)
@bp.route('/user_directory')
@login_required
@roles_required('admin', 'qc')
def user_directory():
    """全系统用户目录 - 按中文名归集显示"""
    search_term = request.args.get('search', '').strip()
    query = SystemAccount.query
    if search_term:
        query = query.filter(or_(SystemAccount.username.ilike(f'%{search_term}%'), SystemAccount.chinese_name.ilike(f'%{search_term}%')))
    
    # 查询出所有符合条件的账户，并按中文名和用户名排序
    accounts = query.order_by(SystemAccount.chinese_name, SystemAccount.username).all()

    # --- 核心修改：在后端按中文名对账户进行分组 ---
    accounts_by_person = defaultdict(list)
    for acc in accounts:
        # 确保只显示那些至少在一个系统中有权限的账户
        if acc.system_access.filter_by(is_active=True).first() or acc.workstation_access.filter_by(is_active=True).first():
            accounts_by_person[acc.chinese_name].append(acc)

    return render_template('user_directory.html', title='全系统用户目录', 
                           accounts_by_person=accounts_by_person, # 传递分组后的字典
                           search_term=search_term)

# --- 认证路由 ---

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('routes.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter(User.username.ilike(form.username.data), User.is_active==True).first()
        if user is None or not user.check_password(form.password.data):
            flash('无效的用户名或密码，或账户已被禁用。', 'danger')
            return redirect(url_for('routes.login'))
        login_user(user, remember=form.remember_me.data)
        
        # 登录后根据角色智能跳转
        if user.role == 'qa':
            next_page = url_for('routes.qa_dashboard')
        elif user.role == 'menjin':
            next_page = url_for('menjin.index_page')
        else: # admin 和 qc 默认跳转到首页
            next_page = url_for('routes.index')
        return redirect(next_page)
        
    return render_template('login.html', title='登录', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('routes.login'))

# --- 申请流程 ---

# app/routes.py

# app/routes.py

@bp.route('/user_requests/new', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'qc')
def new_user_request():
    form = UserRequestForm()
    
    # --- 步骤 1: 无论GET还是POST，都先准备好所有需要传递给模板的数据 ---
    
    # a. 用于系统筛选下拉框的数据
    all_groups = Group.query.order_by(Group.id).all()
    all_systems_list = System.query.order_by(System.name).all()
    systems_with_groups = [
        {'id': s.id, 'name': f"{s.system_number} - {s.name}", 'group': s.group.name if s.group else 'none'} 
        for s in all_systems_list
    ]
    
    # b. 用于角色智能推荐 <datalist> 的数据 (之前遗漏的部分)
    # 这一部分现在从JavaScript移到了后端，因为datalist的填充需要后端数据
    # 如果你的JS有更复杂的逻辑，这部分也可以通过新的API实现
    
    # c. 填充目标系统下拉框的 choices
    form.target_system.choices = [(0, '-- 请选择一个系统 --')] + [(s['id'], s['name']) for s in systems_with_groups]

    # --- 步骤 2: 处理表单提交 ---
    if form.validate_on_submit():
        username = form.username.data.strip()
        system_id = form.target_system.data
        existing_pending_request = UserRequest.query.filter_by(
            username=username,
            target_systems=str(system_id),
            status='pending'
        ).first()

        if existing_pending_request:
            flash(f'提交失败：一个针对用户 “{username}” 和该系统的待处理申请已存在...', 'warning')
        else:
            new_req = UserRequest(
                requested_by_id=current_user.id,
                username=username,
                chinese_name=form.chinese_name.data.strip(),
                computer_role=form.computer_role.data.strip() or None,
                workstation_role=form.workstation_role.data.strip() or None,
                target_systems=str(system_id)
            )
            db.session.add(new_req)
            db.session.commit()
            flash(f'用户 “{username}” 的新增申请已成功提交！', 'success')
            return redirect(url_for('routes.new_user_request'))
            
    # --- 步骤 3: 渲染模板，并确保传递所有需要的数据 ---
    return render_template('user_request_form.html', 
                           title='系统用户新增申请', 
                           form=form, 
                           all_groups=all_groups, 
                           systems_with_groups=systems_with_groups)

@bp.route('/my_requests')
@login_required
@roles_required('admin', 'qc')
def my_requests():
    add_reqs = UserRequest.query.filter_by(requested_by_id=current_user.id).order_by(UserRequest.request_date.desc()).all()
    # 使用正确的模型
    disable_reqs = DisableRequest.query.filter_by(requested_by_id=current_user.id).order_by(DisableRequest.request_date.desc()).all()
    role_change_reqs = RoleChangeRequest.query.filter_by(requested_by_id=current_user.id).order_by(RoleChangeRequest.request_date.desc()).all()
    all_systems = {s.id: s for s in System.query.all()}
    return render_template('my_requests.html', title='我的申请记录',
                           add_requests=add_reqs,
                           disable_requests=disable_reqs, # 使用正确的变量名
                           role_change_requests=role_change_reqs,
                           all_systems=all_systems)


@bp.route('/my_requests/<req_type>/<int:request_id>/cancel', methods=['POST'])
@login_required
@roles_required('admin', 'qc')
def cancel_my_request(req_type, request_id):
    # 使用正确的 model_map
    model_map = {
        'add': UserRequest,
        'disable': DisableRequest,
        'role_change': RoleChangeRequest
    }
    Model = model_map.get(req_type)
    if not Model:
        flash('无效的申请类型。', 'danger')
        return redirect(url_for('routes.my_requests'))
    req = Model.query.get_or_404(request_id)
    if req.requested_by_id != current_user.id:
        flash('您没有权限撤销此申请。', 'danger')
        return redirect(url_for('routes.my_requests'))
    if req.status == 'pending':
        db.session.delete(req)
        db.session.commit()
        flash('申请已成功撤销。', 'success')
    else:
        flash('无法撤销一个已被管理员处理的申请。', 'warning')
    return redirect(url_for('routes.my_requests'))




@bp.route('/user_requests/role_change', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'qc')
def new_role_change_request():
    form = RoleChangeRequestForm()
    form.system.choices = [(0, '-- 请先选择一个系统 --')] + [(s.id, s.name) for s in System.query.order_by(System.name).all()]
    if request.method == 'POST':
        system_id = form.system.data
        if system_id:
            system = System.query.get(system_id)
            form.computer_user_link.choices = [(su.id, su.account.chinese_name) for su in system.system_users]
            form.workstation_user_link.choices = [(wu.id, wu.account.chinese_name) for wu in system.workstation_users]
        else:
            form.computer_user_link.choices = []
            form.workstation_user_link.choices = []
    if form.validate_on_submit():
        if form.computer_user_link.data and form.new_computer_role.data:
            link = SystemUser.query.get(form.computer_user_link.data)
            if not link:
                flash('找不到指定的电脑用户。', 'danger')
                return redirect(url_for('routes.new_role_change_request'))
            req = RoleChangeRequest(requested_by_id=current_user.id, system_id=link.system_id, account_id=link.account_id, user_type='computer', current_role=link.system_role, new_role=form.new_computer_role.data.strip())
            db.session.add(req)
            db.session.commit()
            flash('电脑用户角色修改申请已提交。', 'success')
            return redirect(url_for('routes.index'))
        elif form.workstation_user_link.data and form.new_workstation_role.data:
            link = WorkstationUser.query.get(form.workstation_user_link.data)
            if not link:
                flash('找不到指定的工作站用户。', 'danger')
                return redirect(url_for('routes.new_role_change_request'))
            req = RoleChangeRequest(requested_by_id=current_user.id, system_id=link.system_id, account_id=link.account_id, user_type='workstation', current_role=link.role.name, new_role=form.new_workstation_role.data.strip())
            db.session.add(req)
            db.session.commit()
            flash('工作站用户角色修改申请已提交。', 'success')
            return redirect(url_for('routes.index'))
        else:
            flash('请完整填写一个修改申请（电脑或工作站）。', 'warning')
    return render_template('role_change_request_form.html', title='系统用户角色修改申请', form=form)



# --- 管理员功能路由 ---
@bp.route('/user_requests/disable_person/<string:chinese_name>', methods=['POST'])
@login_required
@roles_required('admin', 'qc')
def request_person_disable(chinese_name):
    accounts_to_disable = SystemAccount.query.filter_by(chinese_name=chinese_name).all()
    if not accounts_to_disable:
        flash(f'找不到中文名为 “{chinese_name}” 的用户。', 'danger')
        return redirect(url_for('routes.user_directory'))
    created_count = 0
    for account in accounts_to_disable:
        if not DisableRequest.query.filter_by(account_to_disable_id=account.id, status='pending').first():
            new_request = DisableRequest(account_to_disable_id=account.id, requested_by_id=current_user.id)
            db.session.add(new_request)
            created_count += 1
    db.session.commit()
    if created_count > 0:
        flash(f'已为 “{chinese_name}” 的所有活动系统账户提交禁用申请。', 'success')
    else:
        flash(f'“{chinese_name}” 的所有活动系统账户都已有待处理的禁用申请。', 'warning')
    return redirect(url_for('routes.user_directory'))

@bp.route('/user/request_partial_disable/<string:chinese_name>', methods=['POST'])
@login_required
@roles_required('admin', 'qc')
def request_partial_disable(chinese_name):
    comp_link_ids = request.form.getlist('computer_links', type=int)
    ws_link_ids = request.form.getlist('workstation_links', type=int)
    if not comp_link_ids and not ws_link_ids:
        flash('您没有选择任何要禁用的权限。', 'warning')
        return redirect(url_for('routes.user_directory'))
    comp_links_info = []
    if comp_link_ids:
        links = SystemUser.query.filter(SystemUser.id.in_(comp_link_ids)).all()
        for link in links: comp_links_info.append({"id": link.id, "system": link.system.name, "role": link.system_role})
    ws_links_info = []
    if ws_link_ids:
        links = WorkstationUser.query.filter(WorkstationUser.id.in_(ws_link_ids)).all()
        for link in links: ws_links_info.append({"id": link.id, "system": link.system.name, "role": link.role.name})
    new_req = PartialDisableRequest(
        requested_by_id=current_user.id,
        chinese_name=chinese_name,
        system_user_links=json.dumps(comp_links_info) if comp_links_info else None,
        workstation_user_links=json.dumps(ws_links_info) if ws_links_info else None
    )
    db.session.add(new_req)
    db.session.commit()
    flash(f'为用户 “{chinese_name}” 禁用部分权限的申请已提交。', 'success')
    return redirect(url_for('routes.user_directory'))



@bp.route('/admin/requests')
@login_required
@roles_required('admin', 'qc')
def pending_requests():
    add_reqs = UserRequest.query.filter_by(status='pending').order_by(UserRequest.request_date.desc()).all()
    disable_reqs = DisableRequest.query.filter_by(status='pending').order_by(DisableRequest.request_date.desc()).all()
    role_change_reqs = RoleChangeRequest.query.filter_by(status='pending').order_by(RoleChangeRequest.request_date.desc()).all()
    menjin_del_reqs = MenjinDeletionRequest.query.filter_by(status='pending').order_by(MenjinDeletionRequest.request_date.desc()).all()
    partial_disable_reqs = PartialDisableRequest.query.filter_by(status='pending').order_by(PartialDisableRequest.request_date.desc()).all()
    
    all_systems = {s.id: s for s in System.query.all()}
    return render_template('admin_pending_requests.html', title='待执行申请', 
                           add_requests=add_reqs, 
                           disable_requests=disable_reqs,
                           role_change_requests=role_change_reqs,
                           menjin_del_requests=menjin_del_reqs,
                           partial_disable_requests=partial_disable_reqs,
                           all_systems=all_systems)

@bp.route('/admin/requests/add/<int:request_id>/approve', methods=['POST'])
@login_required
@roles_required('admin', 'qc')
def approve_add_request(request_id):
    req = UserRequest.query.get_or_404(request_id)
    # 使用“找到或创建”逻辑
    account = find_or_create_system_account(req.username, req.chinese_name)
    
    system_ids = [int(sid) for sid in req.target_systems.split(',')]
    for sid in system_ids:
        if req.computer_role:
            # 同样增加重复检查
            if not SystemUser.query.filter_by(account_id=account.id, system_id=sid, system_role=req.computer_role).first():
                db.session.add(SystemUser(account_id=account.id, system_id=sid, system_role=req.computer_role))
        if req.workstation_role:
            role = SystemRole.query.filter_by(name=req.workstation_role).first()
            if not role:
                role = SystemRole(name=req.workstation_role)
                db.session.add(role)
                db.session.flush()
            # 同样增加重复检查
            if not WorkstationUser.query.filter_by(account_id=account.id, system_id=sid, role_id=role.id).first():
                db.session.add(WorkstationUser(account_id=account.id, system_id=sid, role_id=role.id))
                
    req.status = 'completed'
    db.session.commit()
    flash(f'用户 "{req.chinese_name}" 的新增申请已处理完成。', 'success')
    return redirect(url_for('routes.pending_requests'))



@bp.route('/admin/requests/menjin_delete/<int:request_id>/approve', methods=['POST'])
@login_required
@roles_required('admin')
def approve_menjin_del_request(request_id):
    from menjin.routes import execute_stored_procedure, get_sp_error_message
    req = MenjinDeletionRequest.query.get_or_404(request_id)
    
    # 调用 menjin 的函数来执行存储过程
    _, ret_code, db_error = execute_stored_procedure('sp_wg2014_ConsumerDelete', (req.consumer_no,))

    if ret_code == 0:
        req.status = 'completed'
        db.session.commit()
        flash(f'门禁用户 "{req.consumer_name}" (工号: {req.consumer_no}) 已成功删除。', 'success')
    else:
        req.status = 'failed'
        db.session.commit()
        error_message = get_sp_error_message(ret_code)
        flash(f'删除门禁用户 "{req.consumer_name}" 失败: {error_message} {db_error or ""}', 'danger')
        
    return redirect(url_for('routes.pending_requests'))

@bp.route('/admin/requests/partial_disable/<int:request_id>/approve', methods=['POST'])
@login_required
@roles_required('admin')
def approve_partial_disable_request(request_id):
    req = PartialDisableRequest.query.get_or_404(request_id)
    comp_links_info = req.get_system_links()
    ws_links_info = req.get_workstation_links()
    disabled_count = 0
    if comp_links_info:
        ids_to_disable = [link['id'] for link in comp_links_info]
        disabled_count += SystemUser.query.filter(SystemUser.id.in_(ids_to_disable)).update({'is_active': False}, synchronize_session=False)
    if ws_links_info:
        ids_to_disable = [link['id'] for link in ws_links_info]
        disabled_count += WorkstationUser.query.filter(WorkstationUser.id.in_(ids_to_disable)).update({'is_active': False}, synchronize_session=False)
    req.status = 'completed'
    db.session.commit()
    flash(f'已为用户 “{req.chinese_name}” 成功禁用了 {disabled_count} 项系统权限。', 'success')
    return redirect(url_for('routes.pending_requests'))
@bp.route('/admin/requests/partial_disable/<int:request_id>/cancel', methods=['POST'])
@login_required
@roles_required('admin')
def cancel_partial_disable_request(request_id):
    # 查询的模型应该是 PartialDisableRequest，确保你的 models.py 中已经重命名
    # 如果还没有，请将下面的 PartialDisableRequest 改回 PartialDeletionRequest
    req = PartialDisableRequest.query.get_or_404(request_id)
    
    if req.status == 'pending':
        try:
            # 在删除对象前，先把名字存下来用于 flash 消息
            chinese_name_to_flash = req.chinese_name
            
            db.session.delete(req)
            db.session.commit()
            
            # 更新 flash 消息文本
            flash(f'已成功撤销对 “{chinese_name_to_flash}” 的部分禁用申请。', 'success')
        except Exception as e:
            db.session.rollback()
            # 在后台记录详细错误
            print(f"Error cancelling partial disable request {request_id}: {e}")
            flash('撤销申请时发生错误，请联系管理员。', 'danger')
    else:
        flash('无法撤销一个已被处理的申请。', 'warning')
        
    return redirect(url_for('routes.pending_requests'))


@bp.route('/admin/requests/menjin_delete/<int:request_id>/cancel', methods=['POST'])
@login_required
@roles_required('admin')
def cancel_menjin_del_request(request_id):
    req = MenjinDeletionRequest.query.get_or_404(request_id)
    if req.status == 'pending':
        # 在删除对象前，先把名字存下来用于 flash 消息
        consumer_name_to_flash = req.consumer_name
        
        db.session.delete(req)
        db.session.commit()
        flash(f'已成功撤销对门禁用户 “{consumer_name_to_flash}” 的删除申请。', 'success')
    else:
        flash('无法撤销一个已被处理的申请。', 'warning')
    return redirect(url_for('routes.pending_requests'))

@bp.route('/admin/requests/role_change/<int:request_id>/cancel', methods=['POST'])
@login_required
@roles_required('admin')
def cancel_role_change_request(request_id):
    """管理员撤销一个用户角色修改申请"""
    req = RoleChangeRequest.query.get_or_404(request_id)
    
    if req.status == 'pending':
        # 核心修正：在删除对象之前，先把需要用到的信息存下来
        user_name_to_flash = req.account.chinese_name
        
        # 现在可以安全地删除对象了
        db.session.delete(req)
        db.session.commit()
        
        # 使用之前存好的变量来构造提示消息
        flash(f'已成功撤销对 “{user_name_to_flash}” 的角色修改申请。', 'success')
    else:
        flash('无法撤销一个已处理的申请。', 'warning')
        
    return redirect(url_for('routes.pending_requests'))

@bp.route('/admin/requests/add/<int:request_id>/cancel', methods=['POST'])
@login_required
@roles_required('admin')
def cancel_add_request(request_id):
    req = UserRequest.query.get_or_404(request_id)
    if req.status == 'pending':
        db.session.delete(req)
        db.session.commit()
        flash(f'已成功撤销对 “{req.chinese_name}” 的新增申请。', 'success')
    else:
        flash('无法撤销一个已处理的申请。', 'warning')
    return redirect(url_for('routes.pending_requests'))

@bp.route('/admin/requests/disable/<int:request_id>/approve', methods=['POST'])
@login_required
@roles_required('admin')
def approve_disable_request(request_id):
    req = DisableRequest.query.get_or_404(request_id)
    account_to_disable = req.account_to_disable
    
    # 核心修正：添加 synchronize_session=False 参数
    SystemUser.query.filter_by(account_id=account_to_disable.id).update({'is_active': False}, synchronize_session=False)
    WorkstationUser.query.filter_by(account_id=account_to_disable.id).update({'is_active': False}, synchronize_session=False)
    
    req.status = 'completed'
    db.session.commit()
    
    flash(f'用户 "{account_to_disable.chinese_name}" 的所有系统权限已禁用。', 'success')
    return redirect(url_for('routes.pending_requests'))

@bp.route('/admin/requests/disable/<int:request_id>/cancel', methods=['POST'])
@login_required
@roles_required('admin')
def cancel_disable_request(request_id):
    req = DisableRequest.query.get_or_404(request_id)
    if req.status == 'pending':
        user_name_to_flash = req.account_to_disable.chinese_name
        db.session.delete(req)
        db.session.commit()
        flash(f'已成功撤销对用户 “{user_name_to_flash}” 的禁用申请。', 'success')
    else:
        flash('无法撤销一个已处理的申请。', 'warning')
    return redirect(url_for('routes.pending_requests'))


@bp.route('/admin/requests/delete/<int:request_id>/cancel', methods=['POST'])
@login_required
@roles_required('admin')
def cancel_del_request(request_id):
    req = DisableRequest.query.get_or_404(request_id)
    if req.status == 'pending':
        user_name_to_flash = req.account_to_delete.chinese_name
        db.session.delete(req)
        db.session.commit()
        flash(f'已成功撤销对用户 “{user_name_to_flash}” 的删除申请。', 'success')
    else:
        flash('无法撤销一个已处理的申请。', 'warning')
    return redirect(url_for('routes.pending_requests'))

@bp.route('/admin/users')
@login_required
@roles_required('admin')
def manage_users():
    users = User.query.order_by(User.username).all()
    return render_template('manage_users.html', title='平台用户管理', users=users)

@bp.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def edit_user(user_id):
    user = User.query.get_or_404(user_id) if user_id != 0 else None
    form = AdminUserForm(original_username=user.username if user else None)
    if form.validate_on_submit():
        if not user:
            user = User()
            db.session.add(user)
            if not form.password.data:
                flash('新用户必须设置密码。', 'danger')
                return render_template('edit_user.html', title='创建用户', form=form, user=user)
        user.username = form.username.data.strip()
        user.chinese_name = form.chinese_name.data.strip()
        user.role = form.role.data
        user.is_active = form.is_active.data
        if form.password.data:
            user.set_password(form.password.data)
            flash('用户密码已更新。', 'info')
        db.session.commit()
        flash('用户信息已成功保存。', 'success')
        return redirect(url_for('routes.manage_users'))
    if user and request.method == 'GET':
        form.process(obj=user)
        form.password.data = ""
    title = '编辑用户' if user else '创建新用户'
    return render_template('edit_user.html', title=title, form=form, user=user)

@bp.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
@roles_required('admin')
def delete_user(user_id):
    user_to_delete = User.query.get_or_404(user_id)
    if user_to_delete.id == current_user.id:
        flash('不能删除您自己的账户。', 'danger')
        return redirect(url_for('routes.manage_users'))
    if user_to_delete.role == 'admin':
        admin_count = User.query.filter_by(role='admin', is_active=True).count()
        if admin_count <= 1:
            flash('不能删除最后一个有效的管理员账户。', 'danger')
            return redirect(url_for('routes.manage_users'))
    db.session.delete(user_to_delete)
    db.session.commit()
    flash(f'平台用户 "{user_to_delete.username}" 已被成功删除。', 'success')
    return redirect(url_for('routes.manage_users'))

# app/routes.py

# ... (其他路由不变) ...

@bp.route('/system/<int:system_id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def edit_system(system_id):
    system = System.query.get_or_404(system_id)
    # 核心修正 1: 根据请求方法来决定如何初始化表单
    # POST 请求时，我们传入 request.form 来加载用户提交的数据
    # GET 请求时，我们不传 request.form，让表单为空
    form = EditSystemForm(request.form if request.method == 'POST' else None, 
                          original_system_number=system.system_number)
    
    # 动态填充分组下拉框的选项 (对 GET 和 POST 都需要)
    populate_group_choices(form)

    if form.validate_on_submit():
        # --- 数据保存逻辑 (这个逻辑是正确的，保持不变) ---
        system.name = form.name.data.strip()
        system.system_number = form.system_number.data.strip()
        system.group_id = form.group.data if form.group.data != 0 else None
        system.check_frequency_days = form.check_frequency_days.data
        system.notes = form.notes.data.strip()
        system.is_domain_joined = form.is_domain_joined.data
        system.is_workstation_domain_joined = form.is_workstation_domain_joined.data
        system.computer_name = form.computer_name.data.strip()
        system.ip_address = form.ip_address.data.strip()
        system.backup_method = form.backup_method.data
        system.backup_frequency = form.backup_frequency.data
        
        try:
            db.session.commit()
            flash('系统信息已成功更新！', 'success')
            return redirect(url_for('routes.system_detail', system_id=system.id))
        except Exception as e:
            db.session.rollback()
            flash(f'更新失败: {e}', 'danger')

    # 核心修正 2: 在 GET 请求时，用数据库对象的数据来明确地填充表单
    elif request.method == 'GET':
        form.name.data = system.name
        form.system_number.data = system.system_number
        form.group.data = system.group_id
        form.check_frequency_days.data = system.check_frequency_days
        form.notes.data = system.notes
        form.is_domain_joined.data = system.is_domain_joined
        form.is_workstation_domain_joined.data = system.is_workstation_domain_joined
        form.computer_name.data = system.computer_name
        form.ip_address.data = system.ip_address
        form.backup_method.data = system.backup_method
        form.backup_frequency.data = system.backup_frequency

    # 如果是 POST 请求且验证失败，WTForms 会自动保留用户输入的数据并显示错误
    # 如果是 GET 请求，上面的代码块已经用数据库数据填充了表单
    return render_template('edit_system.html', title='编辑系统', form=form, system=system)
@bp.route('/admin/groups', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def manage_groups():
    form = GroupForm()
    if form.validate_on_submit():
        new_group = Group(name=form.name.data.strip())
        db.session.add(new_group)
        db.session.commit()
        flash(f'分组 "{new_group.name}" 已成功创建。', 'success')
        return redirect(url_for('routes.manage_groups'))
    groups = Group.query.order_by(Group.id).all()
    return render_template('manage_groups.html', title='管理分组', form=form, groups=groups)

@bp.route('/admin/groups/edit/<int:group_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def edit_group(group_id):
    group = Group.query.get_or_404(group_id)
    form = GroupForm(original_name=group.name)
    if form.validate_on_submit():
        group.name = form.name.data.strip()
        db.session.commit()
        flash('分组名称已成功更新。', 'success')
        return redirect(url_for('routes.manage_groups'))
    elif request.method == 'GET':
        form.name.data = group.name
    return render_template('edit_group.html', title='编辑分组', form=form, group=group)

@bp.route('/admin/groups/delete/<int:group_id>', methods=['POST'])
@login_required
@roles_required('admin')
def delete_group(group_id):
    group_to_delete = Group.query.get_or_404(group_id)
    if group_to_delete.systems.first():
        flash(f'无法删除分组 "{group_to_delete.name}"，因为它仍被系统使用。', 'danger')
    else:
        db.session.delete(group_to_delete)
        db.session.commit()
        flash(f'分组 "{group_to_delete.name}" 已成功删除。', 'success')
    return redirect(url_for('routes.manage_groups'))

@bp.route('/qa/toggle_need/<int:system_id>', methods=['POST'])
@login_required
@roles_required('admin','qa')
def toggle_qa_check_need(system_id):
    """切换一个系统是否需要QA核查"""
    system = System.query.get_or_404(system_id)
    system.needs_qa_check = not system.needs_qa_check
    db.session.commit()
    status = "需要" if system.needs_qa_check else "不再需要"
    flash(f'系统 “{system.name}” 已被标记为 “{status}” QA核查。', 'info')
    return redirect(url_for('routes.qa_dashboard'))


@bp.route('/execute')
@login_required
@roles_required('admin')
def execute_dashboard():
    systems = System.query.filter(System.computer_name.isnot(None), System.computer_name != '').order_by(System.name).all()
    scripts = Script.query.order_by(Script.name).all()
    recent_jobs = Job.query.order_by(Job.created_at.desc()).limit(20).all()
    latest_jobs = {s.id: Job.query.filter_by(system_id=s.id).order_by(Job.created_at.desc()).first() for s in systems}
    return render_template('execute_dashboard.html', title='远程脚本执行', systems=systems, scripts=scripts, recent_jobs=recent_jobs, latest_jobs=latest_jobs)

@bp.route('/admin/scripts', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def manage_scripts():
    form = ScriptForm()
    if form.validate_on_submit():
        script_name = form.name.data.strip()
        if Script.query.filter(Script.name.ilike(script_name)).first():
            flash('该脚本名称已存在。', 'danger')
        else:
            new_script = Script(name=script_name, description=form.description.data.strip(), content=form.content.data)
            db.session.add(new_script)
            db.session.commit()
            flash('新脚本已成功创建。', 'success')
            return redirect(url_for('routes.manage_scripts'))
    scripts = Script.query.order_by(Script.name).all()
    return render_template('manage_scripts.html', title='脚本管理', form=form, scripts=scripts)

@bp.route('/admin/scripts/edit/<int:script_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def edit_script(script_id):
    script = Script.query.get_or_404(script_id)
    form = ScriptForm(obj=script)
    if form.validate_on_submit():
        new_name = form.name.data.strip()
        existing_script = Script.query.filter(Script.name.ilike(new_name)).first()
        if existing_script and existing_script.id != script_id:
            flash('该脚本名称已被其他脚本使用。', 'danger')
        else:
            script.name, script.description, script.content = new_name, form.description.data.strip(), form.content.data
            db.session.commit()
            flash('脚本已成功更新。', 'success')
            return redirect(url_for('routes.manage_scripts'))
    return render_template('edit_script.html', title='编辑脚本', form=form, script=script)

@bp.route('/admin/scripts/delete/<int:script_id>', methods=['POST'])
@login_required
@roles_required('admin')
def delete_script(script_id):
    script = Script.query.get_or_404(script_id)
    if Job.query.filter_by(script_id=script.id).first():
        flash('无法删除此脚本，因为它已被用于执行任务。', 'danger')
    else:
        db.session.delete(script)
        db.session.commit()
        flash('脚本已成功删除。', 'success')
    return redirect(url_for('routes.manage_scripts'))

# --- 数据操作路由 ---




@bp.route('/system/add', methods=['POST'])
@login_required
@roles_required('admin')
def add_system():
    form = AddSystemForm()
    form.group.choices = [(0, 'Do not assign group')] + [(g.id, g.name) for g in Group.query.order_by(Group.name).all()]
    if form.validate_on_submit():
        new_system = System(name=form.name.data.strip(), system_number=form.system_number.data.strip(), group_id=form.group.data if form.group.data != 0 else None, check_frequency_days=form.check_frequency_days.data, next_check_date=form.next_check_date.data, is_domain_joined=form.is_domain_joined.data, computer_name=form.computer_name.data.strip(), ip_address=form.ip_address.data.strip())
        db.session.add(new_system)
        db.session.commit()
        flash('New system has been added successfully!', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Failed to add: {getattr(form, field).label.text} - {error}", "danger")
    return redirect(url_for('routes.index'))

@bp.route('/admin/requests/role_change/<int:request_id>/approve', methods=['POST'])
@login_required
@roles_required('admin')
def approve_role_change_request(request_id):
    req = RoleChangeRequest.query.get_or_404(request_id)
    
    if req.user_type == 'computer':
        # 核心修正：将 current_role 改为 system_role
        link = SystemUser.query.filter_by(
            system_id=req.system_id, 
            account_id=req.account_id, 
            system_role=req.current_role  # <-- 这里是关键的修正
        ).first()
        
        if link:
            link.system_role = req.new_role
            flash(f'电脑用户 “{req.account.chinese_name}” 在系统 “{req.system.name}” 中的角色已更新。', 'success')
        else:
            flash(f'操作失败：找不到原始的电脑用户权限记录。可能已被修改或删除。', 'danger')

    elif req.user_type == 'workstation':
        link = WorkstationUser.query.join(SystemRole).filter(
            WorkstationUser.system_id==req.system_id, 
            WorkstationUser.account_id==req.account_id, 
            SystemRole.name==req.current_role
        ).first()
        
        if link:
            new_role_obj = SystemRole.query.filter(SystemRole.name.ilike(req.new_role)).first()
            if not new_role_obj:
                new_role_obj = SystemRole(name=req.new_role)
                db.session.add(new_role_obj)
                db.session.flush()
            link.role_id = new_role_obj.id
            flash(f'工作站用户 “{req.account.chinese_name}” 在系统 “{req.system.name}” 中的角色已更新。', 'success')
        else:
            flash(f'操作失败：找不到原始的工作站用户权限记录。可能已被修改或删除。', 'danger')

    req.status = 'completed'
    db.session.commit()
    return redirect(url_for('routes.pending_requests'))


@bp.route('/system/<int:system_id>/update_dates', methods=['POST'])
@login_required
@roles_required('admin')
def update_dates(system_id):
    system = System.query.get_or_404(system_id)
    last_date_str = request.form.get('last_check_date')
    if last_date_str:
        try:
            last_check_date = date.fromisoformat(last_date_str)
            system.last_check_date = last_check_date
            if system.check_frequency_days:
                system.next_check_date = last_check_date + timedelta(days=system.check_frequency_days)
            flash(f'系统 "{system.name}" 的核查日期已更新，下一次核查日期已自动计算。', 'success')
        except ValueError:
            flash('输入的日期格式无效。', 'danger')
    else:
        next_date_str = request.form.get('next_check_date')
        if next_date_str:
            system.next_check_date = date.fromisoformat(next_date_str)
            flash(f'系统 "{system.name}" 的下一次核查日期已手动更新。', 'info')
    db.session.commit()
    return redirect(url_for('routes.it_check_manage'))

@bp.route('/system/delete/<int:system_id>', methods=['POST'])
@login_required
@roles_required('admin')
def delete_system(system_id):
    system = System.query.get_or_404(system_id)
    if system.system_users.first() or system.workstation_users.first():
        flash(f'无法删除系统 "{system.name}"，因为它仍有关联的用户。', 'danger')
        return redirect(url_for('routes.index'))
    if Job.query.filter_by(system_id=system.id).first():
        flash(f'无法删除系统 "{system.name}"，因为它存在关联的任务执行记录。', 'danger')
        return redirect(url_for('routes.index'))
    db.session.delete(system)
    db.session.commit()
    flash(f'系统 "{system.name}" 已被成功删除。', 'success')
    return redirect(url_for('routes.it_check_manage'))

@bp.route('/system/<int:system_id>/check_from_index', methods=['POST'])
@login_required
@roles_required('admin')
def perform_check_from_index(system_id):
    system = System.query.get_or_404(system_id)
    today = date.today()
    history_note = f"管理员 {current_user.chinese_name} 在主页快速完成了常规核查。"
    new_check = CheckHistory(system_id=system.id, check_date=today, checked_by=current_user.chinese_name, notes=history_note)
    db.session.add(new_check)
    system.last_check_date = today
    if system.check_frequency_days:
        system.next_check_date = today + timedelta(days=system.check_frequency_days)
    db.session.commit()
    flash(f'系统 "{system.name}" 已核查，下一次核查时间已更新。', 'success')
    return redirect(url_for('routes.it_check_manage'))

@bp.route('/restore/update/<int:system_id>', methods=['POST'])
@login_required
@roles_required('admin')
def update_restore_info(system_id):
    system = System.query.get_or_404(system_id)
    system.is_restore_verified = 'is_restore_verified' in request.form
    last_date_str = request.form.get('last_restore_verification_date')
    if last_date_str:
        try:
            system.last_restore_verification_date = date.fromisoformat(last_date_str)
        except (ValueError, TypeError):
            system.last_restore_verification_date = None
    else:
        system.last_restore_verification_date = None
    cycle = request.form.get('restore_verification_cycle', 0, type=int)
    system.restore_verification_cycle = cycle if cycle > 0 else None
    db.session.commit()
    flash(f'系统 "{system.name}" 的备份还原验证信息已更新。', 'success')
    return redirect(url_for('routes.restore_dashboard'))

@bp.route('/qa/update_dates/<int:system_id>', methods=['POST'])
@login_required
@roles_required('admin', 'qa')
def update_qa_dates(system_id):
    system = System.query.get_or_404(system_id)
    last_date_str = request.form.get('qa_last_check_date')
    frequency = request.form.get('qa_check_frequency_days', type=int)
    system.qa_check_frequency_days = frequency
    if last_date_str:
        try:
            last_check_date = date.fromisoformat(last_date_str)
            system.qa_last_check_date = last_check_date
            if frequency:
                system.qa_next_check_date = last_check_date + timedelta(days=frequency)
            flash(f'系统 "{system.name}" 的QA核查日期已更新。', 'success')
        except ValueError:
            flash('输入的日期格式无效。', 'danger')
    db.session.commit()
    return redirect(url_for('routes.qa_dashboard'))

@bp.route('/qa/check/<int:system_id>', methods=['POST'])
@login_required
@roles_required('admin', 'qa')
def perform_qa_check(system_id):
    system = System.query.get_or_404(system_id)
    today = date.today()
    system.qa_last_check_date = today
    if system.qa_check_frequency_days:
        system.qa_next_check_date = today + timedelta(days=system.qa_check_frequency_days)
        flash(f'系统 "{system.name}" 的QA核查已完成，下一次核查时间已更新。', 'success')
    else:
        flash('请先为该系统设置一个QA核查周期。', 'warning')
    db.session.commit()
    return redirect(url_for('routes.qa_dashboard'))
    
@bp.route('/assign_group/<int:user_id>', methods=['POST'])
@login_required
@roles_required('admin')
def assign_group(user_id):
    user = User.query.get_or_404(user_id)
    form = AssignGroupForm(prefix=f"form-{user.id}")
    form.group.choices = [(g.id, g.name) for g in Group.query.order_by(Group.name).all()]
    if form.validate_on_submit():
        user.group_id = form.group.data
        db.session.commit()
        flash(f'用户 "{user.chinese_name}" 的分组已成功更新。', 'success')
    return redirect(url_for('routes.user_directory', 
                            search_query=request.args.get('search_query', ''), 
                            group=request.args.get('group', '0')))

@bp.route('/job/cancel/<int:job_id>', methods=['POST'])
@login_required
@roles_required('admin')
def cancel_job(job_id):
    job_to_cancel = Job.query.get_or_404(job_id)
    if job_to_cancel.status == 'pending':
        db.session.delete(job_to_cancel)
        db.session.commit()
        flash(f'任务ID {job_id} 已成功取消。', 'success')
    else:
        flash(f'无法取消任务ID {job_id}，因为它已经在运行或已完成。', 'warning')
    if 'execute' in request.referrer:
        return redirect(url_for('routes.execute_dashboard'))
    return redirect(request.referrer or url_for('routes.index'))

# --- API Routes ---
@bp.route('/api/system/<int:system_id>/roles')
@login_required
def get_system_roles_api(system_id):
    """API: 获取指定系统下所有不重复的角色，用于智能推荐"""
    
    computer_roles = [
        r[0] for r in db.session.query(SystemUser.system_role)
        .filter(SystemUser.system_id == system_id)
        .distinct().all() if r[0]
    ]
    
    workstation_roles = [
        role.name for role in SystemRole.query
        .join(WorkstationUser)
        .filter(WorkstationUser.system_id == system_id)
        .distinct().order_by(SystemRole.name).all()
    ]
    
    return jsonify({
        'computer_roles': sorted(list(set(computer_roles))),
        'workstation_roles': sorted(list(set(workstation_roles)))
    })

@bp.route('/api/user/<string:chinese_name>/access_links')
@login_required
def get_user_access_links(chinese_name):
    accounts = SystemAccount.query.filter_by(chinese_name=chinese_name).all()
    if not accounts:
        return jsonify({'error': 'User not found'}), 404
        
    computer_links = []
    workstation_links = []
    
    for acc in accounts:
        for su in acc.system_access:
            computer_links.append({'id': su.id, 'system_name': su.system.name, 'role': su.system_role})
        for wu in acc.workstation_access:
            workstation_links.append({'id': wu.id, 'system_name': wu.system.name, 'role': wu.role.name})
            
    return jsonify({'computer_links': computer_links, 'workstation_links': workstation_links})


@bp.route('/api/system/<int:system_id>/computer_users_for_select')
@login_required
def get_computer_users_for_select(system_id):
    system = System.query.get_or_404(system_id)
    users = [{'id': su.id, 'text': f"{su.account.chinese_name} ({su.account.username}) - 当前角色: {su.system_role}"} for su in system.system_users]
    return jsonify(users)

@bp.route('/api/system/<int:system_id>/workstation_users_for_select')
@login_required
def get_workstation_users_for_select(system_id):
    system = System.query.get_or_404(system_id)
    users = [{'id': wu.id, 'text': f"{wu.account.chinese_name} ({wu.account.username}) - 当前角色: {wu.role.name}"} for wu in system.workstation_users]
    return jsonify(users)


@bp.route('/api/system/<int:system_id>/users')
@login_required
def get_system_users_api(system_id):
    """API: 获取指定系统下的所有用户及其角色，用于参考显示"""
    system = System.query.get_or_404(system_id)
    user_map = {}
    
    # 汇总电脑用户
    for su in system.system_users:
        key = f"{su.account.chinese_name} ({su.account.username})"
        if key not in user_map:
            user_map[key] = []
        user_map[key].append(f"电脑用户: {su.system_role}")
    
    # 汇总工作站用户
    for wu in system.workstation_users:
        key = f"{wu.account.chinese_name} ({wu.account.username})"
        if key not in user_map:
            user_map[key] = []
        user_map[key].append(f"工作站: {wu.role.name}")
        
    # 格式化为最终列表
    users = [{'name': name, 'roles': roles} for name, roles in user_map.items()]
    
    # 为前端JS返回一个更友好的格式
    # 为了简化，我们只返回工作站用户
    ws_users = [{'name': wu.account.chinese_name, 'role': wu.role.name} for wu in system.workstation_users]

    return jsonify(ws_users)

@bp.route('/api/system/<int:system_id>/execute_job', methods=['POST'])
@login_required
@roles_required('admin')
def execute_job(system_id):
    system = System.query.get_or_404(system_id)
    script_id = request.json.get('script_id')
    if not script_id:
        return jsonify({'status': 'error', 'message': 'Script ID not provided.'}), 400
    new_job = Job(system_id=system.id, script_id=script_id, requested_by_id=current_user.id, status='pending')
    db.session.add(new_job)
    db.session.commit()
    return jsonify({'status': 'success', 'message': f'Job has been created for {system.computer_name}.', 'job_id': new_job.id})

@bp.route('/api/job/<int:job_id>/status')
@login_required
@roles_required('admin')
def get_job_status(job_id):
    job = Job.query.get_or_404(job_id)
    return jsonify({'status': job.status, 'output': job.output, 'completed_at': job.completed_at.strftime('%Y-%m-%d %H:%M:%S') if job.completed_at else None})

@bp.route('/api/agent/heartbeat', methods=['POST'])
def agent_heartbeat():
    data = request.json
    hostname = data.get('hostname')
    if not hostname:
        return jsonify({'error': 'Hostname is required'}), 400
    system = System.query.filter(System.computer_name.ilike(hostname)).first()
    if not system:
        return jsonify({'job_id': None, 'message': 'Host not registered'})
    pending_job = Job.query.filter_by(system_id=system.id, status='pending').order_by(Job.created_at).first()
    if pending_job:
        pending_job.status = 'running'
        pending_job.started_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'job_id': pending_job.id, 'script_content': pending_job.script.content})
    return jsonify({'job_id': None})

@bp.route('/api/agent/report_job_result', methods=['POST'])
def agent_report_job_result():
    data = request.json
    job_id, status, output = data.get('job_id'), data.get('status'), data.get('output')
    if not job_id:
        return jsonify({'error': 'Job ID is required'}), 400
    job = Job.query.get(job_id)
    if job:
        job.status, job.output, job.completed_at = status, output, datetime.utcnow()
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Job not found'}), 404