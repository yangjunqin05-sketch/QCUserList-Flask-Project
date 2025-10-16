# app/forms.py

from flask_wtf import FlaskForm
from wtforms import (StringField, PasswordField, BooleanField, SubmitField, 
                     SelectField, IntegerField, DateField, TextAreaField,
                     SelectMultipleField, widgets)
from wtforms.validators import DataRequired, NumberRange, Optional, IPAddress, ValidationError, Length, EqualTo
from app.models import System, Group, User,SystemAccount
from wtforms.validators import DataRequired, NumberRange, Optional, IPAddress, ValidationError, Length, EqualTo
import re
# --- 辅助类 ---

class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

# --- 核心表单 ---

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    remember_me = BooleanField('记住我')
    submit = SubmitField('登录')

class SearchUserForm(FlaskForm):
    search_query = StringField('按用户名/中文名搜索', validators=[Optional()])
    group = SelectField('按分组筛选', coerce=int, validators=[Optional()])
    submit = SubmitField('查询')

class AddSystemForm(FlaskForm):
    name = StringField('仪器/系统名称', validators=[DataRequired()])
    system_number = StringField('仪器编号', validators=[DataRequired()])
    group = SelectField('系统分组', coerce=int, validators=[Optional()])
    check_frequency_days = IntegerField('核查频次 (天)', default=90, validators=[DataRequired(), NumberRange(min=1)])
    next_check_date = DateField('下一次核查时间', validators=[Optional()])
    computer_name = StringField('计算机名', validators=[Optional()])
    ip_address = StringField('IP 地址', validators=[Optional(), IPAddress(message="请输入有效的IP地址")])
    is_domain_joined = BooleanField('电脑是否加入域')
    submit = SubmitField('创建系统')
    def validate_system_number(self, system_number):
        if System.query.filter_by(system_number=system_number.data).first():
            raise ValidationError('该仪器编号已存在。')

class AddComputerUserForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    chinese_name = StringField('中文名', validators=[DataRequired()])
    system_role = StringField('电脑角色/权限', validators=[DataRequired()])
    submit_computer = SubmitField('添加电脑用户')

    # 核心修正：只保留空格验证，移除唯一性检查
    
class AddWorkstationUserForm(FlaskForm):
    username = StringField('用户名 ', validators=[DataRequired()])
    chinese_name = StringField('中文名', validators=[DataRequired()])
    role = StringField('工作站角色', validators=[DataRequired()])
    submit_workstation = SubmitField('添加工作站用户')

    # 核心修正：只保留空格验证，移除唯一性检查
    

class RoleChangeRequestForm(FlaskForm):
    system = SelectField('第一步：选择系统', coerce=int, validators=[DataRequired()])
    
    # 这两个字段将由 JavaScript 动态填充
    computer_user_link = SelectField('第二步：选择要修改的电脑用户', coerce=int, validators=[Optional()])
    workstation_user_link = SelectField('或者，选择要修改的工作站用户', coerce=int, validators=[Optional()])
    
    new_computer_role = StringField('第三步：输入新的电脑角色/权限', validators=[Optional()])
    new_workstation_role = StringField('或者，输入新的工作站角色', validators=[Optional()])
    
    submit = SubmitField('提交申请')
class EditSystemForm(FlaskForm):
    name = StringField('仪器/系统名称', validators=[DataRequired()])
    system_number = StringField('仪器编号', validators=[DataRequired()])
    group = SelectField('系统分组', coerce=int, validators=[Optional()])
    check_frequency_days = IntegerField('核查频次 (天)', validators=[DataRequired(), NumberRange(min=1)])
    is_domain_joined = BooleanField('电脑是否加入域')
    computer_name = StringField('计算机名', validators=[Optional()])
    ip_address = StringField('IP 地址', validators=[Optional(), IPAddress(message="请输入有效的IP地址")])
    is_workstation_domain_joined = BooleanField('工作站是否加入域')
    notes = TextAreaField('备注', validators=[Optional()], render_kw={"rows": 4})
    backup_method = SelectField('备份方式', choices=[
        ('', '--- 请选择 ---'), 
        ('avamar自动备份', 'Avamar自动备份'), 
        ('手动（移动硬盘）', '手动（移动硬盘）'), 
        ('手动（优盘转移动硬盘）', '手动（优盘转移动硬盘）'), 
        ('手动转备份电脑自动', '手动转备份电脑自动'),
        ('无需备份', '无需备份'), 
        ('其他', '其他')
    ], validators=[Optional()])
    backup_frequency = SelectField('备份频次', choices=[
        ('', '--- 请选择 ---'), 
        ('每日', '每日'), 
        ('每周', '每周'), 
        ('每月', '每月'), 
        ('每季度', '每季度'), 
        ('每半年', '每半年'), 
        ('其他', '其他')
    ], validators=[Optional()])
    submit = SubmitField('保存更改')
    def __init__(self, *args, **kwargs):
    # 1. 在调用 super() 之前，从 kwargs 中安全地弹出你的自定义参数
    #    pop 方法会获取该值并将其从字典中移除
        self.original_system_number = kwargs.pop('original_system_number', None)
        
        # 2. 现在 kwargs 中已经没有 'original_system_number' 了，可以安全地传递给父类
        super(EditSystemForm, self).__init__(*args, **kwargs)
    def validate_system_number(self, system_number):
        if system_number.data != self.original_system_number and System.query.filter(System.system_number.ilike(system_number.data)).first():
            raise ValidationError('该仪器编号已存在。')

class UserRequestForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=2, max=64)])
    chinese_name = StringField('中文名', validators=[DataRequired(), Length(min=2, max=64)])
    computer_role = StringField('电脑角色/权限 (如需)', validators=[Optional(), Length(max=100)])
    workstation_role = StringField('工作站角色 (如需)', validators=[Optional(), Length(max=100)])
    
    # 核心修改：将 MultiCheckboxField 改为 SelectField
    target_system = SelectField('选择目标系统', coerce=int, validators=[DataRequired(message="请选择一个目标系统。")])
    
    submit = SubmitField('提交申请')
    def validate_username(self, username):
        """
        自定义验证器，确保用户名只包含字母和数字。
        """
        # 正则表达式：^ 和 $ 表示字符串的开始和结束
        # [a-zA-Z0-9]+ 表示一个或多个大小写字母或数字
        if not re.match('^[a-zA-Z0-9]+$', username.data):
            # 如果不匹配，则引发一个验证错误，这个错误消息会显示在前端
            raise ValidationError('用户名只能包含英文字母和数字。')
    # 验证器现在可以保持简单，因为审批端会处理最终逻辑
    def validate_username(self, username):
        if username.data != username.data.strip():
            raise ValidationError('用户名前后不能有空格。')

class AdminUserForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=2, max=64)])
    chinese_name = StringField('中文名', validators=[DataRequired(), Length(min=2, max=64)])
    password = PasswordField('新密码', validators=[Optional(), Length(min=6), EqualTo('password2', message='两次输入的密码必须一致。')])
    password2 = PasswordField('确认新密码', validators=[Optional()])
    role = SelectField('平台角色', choices=[('admin', '管理员'), 
        ('qc', 'QC组'), 
        ('qa', 'QA组'),
        ('menjin', '门禁组')
    ], validators=[DataRequired()])
    is_active = BooleanField('账户已激活', default=True)
    submit = SubmitField('保存用户')
    def __init__(self, original_username=None, *args, **kwargs):
        super(AdminUserForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
    def validate_username(self, username):
        if username.data.strip().lower() != (self.original_username or '').lower():
            if User.query.filter(User.username.ilike(username.data.strip())).first():
                raise ValidationError('该用户名已被使用。')

class AssignGroupForm(FlaskForm):
    group = SelectField('将分组更新为', coerce=int, validators=[DataRequired()])
    submit_group = SubmitField('更新')

class GroupForm(FlaskForm):
    name = StringField('分组名称', validators=[DataRequired()])
    submit = SubmitField('保存')
    def __init__(self, original_name=None, *args, **kwargs):
        super(GroupForm, self).__init__(*args, **kwargs)
        self.original_name = original_name
    def validate_name(self, name):
        if self.original_name and self.original_name.lower() == name.data.lower():
            return
        if Group.query.filter(Group.name.ilike(name.data)).first():
            raise ValidationError('该分组名称已存在。')

class ScriptForm(FlaskForm):
    name = StringField('脚本名称', validators=[DataRequired()])
    description = StringField('脚本描述', validators=[Optional()])
    content = TextAreaField('PowerShell 脚本内容', validators=[DataRequired()], render_kw={"rows": 15, "class": "font-monospace"})
    submit = SubmitField('保存脚本')

class ExecuteJobForm(FlaskForm):
    script = SelectField('选择要执行的脚本', coerce=int, validators=[DataRequired()])
    submit = SubmitField('立即执行')
    
# --- 新增：确保这个类存在 ---
class BatchImportForm(FlaskForm):
    """用于批量导入用户的表单"""
    user_data = TextAreaField('用户数据', validators=[DataRequired()], 
                              render_kw={"rows": 15, "class": "font-monospace", 
                                         "placeholder": "每行一个用户，格式如下：\n用户名,中文名,角色/权限\n\n例如:\nzhangsan,张三,操作员\nlisi,李四,管理员"})
    import_type = SelectField('导入为', choices=[('computer', '电脑用户'), ('workstation', '工作站用户')], validators=[DataRequired()])
    submit = SubmitField('批量导入')