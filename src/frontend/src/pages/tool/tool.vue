<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { Plus, Edit, Delete, View, Search, Refresh } from '@element-plus/icons-vue'
import pluginIcon from '../../assets/plugin.svg'
import {
  getAllToolsAPI,
  getOwnToolsAPI,
  createToolAPI,
  updateToolAPI,
  deleteToolAPI,
  type ToolResponse
} from '../../apis/tool'
import { useUserStore } from '../../store/user'

// 工具类型定义
interface Tool extends ToolResponse {
  user_id: string
  create_time?: string
  update_time?: string
}

// 创建工具表单类型
interface CreateToolForm {
  zh_name: string
  en_name: string
  description: string
  logo_url: string
}

// 更新工具表单类型
interface UpdateToolForm {
  tool_id: string
  zh_name: string
  en_name: string
  description: string
  logo_url: string
}

// 响应式数据
const tools = ref<Tool[]>([])
const loading = ref(false)
const searchKeyword = ref('')
const activeTab = ref('all') // all, own
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const showDeleteConfirm = ref(false)
const deleteConfirmTool = ref<Tool | null>(null)
const currentTool = ref<Tool | null>(null)
const userStore = useUserStore()

// 表单引用
const createFormRef = ref<FormInstance>()
const editFormRef = ref<FormInstance>()

// 表单数据
const createForm = ref<CreateToolForm>({
  zh_name: '',
  en_name: '',
  description: '',
  logo_url: ''
})

const editForm = ref<UpdateToolForm>({
  tool_id: '',
  zh_name: '',
  en_name: '',
  description: '',
  logo_url: ''
})

// 表单验证规则
const createFormRules = {
  zh_name: [
    { required: true, message: '请输入工具中文名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  en_name: [
    { required: true, message: '请输入工具英文名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  description: [
    { required: true, message: '请输入工具描述', trigger: 'blur' },
    { max: 300, message: '描述不能超过300个字符', trigger: 'blur' }
  ],
  logo_url: [
    { required: true, message: '请输入Logo URL', trigger: 'blur' }
  ]
}

const editFormRules = {
  zh_name: [
    { required: true, message: '请输入工具中文名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  en_name: [
    { required: true, message: '请输入工具英文名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  description: [
    { required: true, message: '请输入工具描述', trigger: 'blur' },
    { max: 300, message: '描述不能超过300个字符', trigger: 'blur' }
  ],
  logo_url: [
    { required: true, message: '请输入Logo URL', trigger: 'blur' }
  ]
}

// 计算属性：过滤后的工具列表
const filteredTools = computed(() => {
  let filtered = tools.value

  // 根据搜索关键词过滤
  if (searchKeyword.value) {
    filtered = filtered.filter(tool =>
      tool.zh_name.toLowerCase().includes(searchKeyword.value.toLowerCase()) ||
      tool.en_name.toLowerCase().includes(searchKeyword.value.toLowerCase()) ||
      tool.description.toLowerCase().includes(searchKeyword.value.toLowerCase())
    )
  }

  return filtered
})

// 判断是否为用户自己的工具（可以删除的工具）
const isOwnTool = (tool: Tool) => {
  console.log('=== isOwnTool判断开始 ===')
  console.log('工具数据:', {
    tool_id: tool.tool_id,
    zh_name: tool.zh_name,
    tool_user_id: tool.user_id,
    tool_user_id_type: typeof tool.user_id
  })
  console.log('当前用户数据:', {
    user_id: userStore.userInfo?.id,
    user_id_type: typeof userStore.userInfo?.id
  })

  // 系统提供的工具（user_id = '0'）不能删除
  if (tool.user_id === '0') {
    console.log('系统工具，不能删除')
    return false
  }

  // 在"我的工具"标签页中，所有非系统工具都可以删除
  if (activeTab.value === 'own') {
    console.log('在"我的工具"标签页，允许删除')
    return true
  }

  // 在"全部工具"标签页中，只有当前用户创建的工具可以删除
  // 使用宽松比较，处理可能的类型差异
  const isOwn = String(tool.user_id) === String(userStore.userInfo?.id)
  console.log('工具判断结果:', {
    toolId: tool.tool_id,
    toolUserId: tool.user_id,
    toolUserIdString: String(tool.user_id),
    currentUserId: userStore.userInfo?.id,
    currentUserIdString: String(userStore.userInfo?.id),
    isOwn: isOwn,
    activeTab: activeTab.value,
    isSystemTool: tool.user_id === '0'
  })
  return isOwn
}

// 获取工具列表
const fetchTools = async () => {
  loading.value = true
  try {
    let response
    switch (activeTab.value) {
      case 'own':
        response = await getOwnToolsAPI()
        break
      default:
        response = await getAllToolsAPI()
        break
    }

    if (response.data.status_code === 200) {
      tools.value = response.data.data || []
      console.log('获取到的工具数据:', tools.value)
      console.log('工具数量:', tools.value.length)
      tools.value.forEach((tool, index) => {
        console.log(`工具${index + 1}:`, {
          tool_id: tool.tool_id,
          zh_name: tool.zh_name,
          user_id: tool.user_id,
          user_id_type: typeof tool.user_id
        })
      })
    } else {
      ElMessage.error(response.data.status_message || '获取工具列表失败')
    }
  } catch (error) {
    console.error('获取工具列表失败:', error)
    ElMessage.error('获取工具列表失败')
  } finally {
    loading.value = false
  }
}

// 测试创建对话框
const testShowCreateDialog = () => {
  console.log('=== 测试显示创建对话框 ===')
  console.log('点击了创建按钮')

  // 直接设置对话框显示
  showCreateDialog.value = true

  console.log('设置后showCreateDialog值:', showCreateDialog.value)

  // 显示成功消息
  ElMessage.success('创建工具对话框已打开')
}

// 显示自定义删除确认对话框
const showCustomDeleteConfirm = (tool: Tool) => {
  console.log('显示自定义删除确认对话框:', tool)
  deleteConfirmTool.value = tool
  showDeleteConfirm.value = true
}

// 处理自定义删除确认
const handleCustomDeleteConfirm = async () => {
  if (!deleteConfirmTool.value) return

  console.log('用户确认删除，调用API...')
  try {
    const response = await deleteToolAPI({ tool_id: deleteConfirmTool.value.tool_id })
    console.log('删除API响应:', response)

    if (response.data.status_code === 200) {
      ElMessage.success('工具删除成功')
      console.log('删除成功，刷新工具列表...')
      await fetchTools()
      console.log('工具列表刷新完成')
    } else {
      console.error('删除失败，状态码:', response.data.status_code)
      console.error('错误消息:', response.data.status_message)
      ElMessage.error(response.data.status_message || '删除工具失败')
    }
  } catch (error) {
    console.error('删除过程出错:', error)
    ElMessage.error('删除工具失败: ' + (error as Error).message)
  } finally {
    showDeleteConfirm.value = false
    deleteConfirmTool.value = null
  }
}

// 取消自定义删除确认
const cancelCustomDeleteConfirm = () => {
  console.log('用户取消删除')
  showDeleteConfirm.value = false
  deleteConfirmTool.value = null
}

// 测试ElMessageBox
const testElMessageBox = () => {
  console.log('=== 测试ElMessageBox ===')

  // 先测试ElMessage是否正常工作
  console.log('测试ElMessage...')
  ElMessage.success('ElMessage测试消息')

  // 延迟后测试alert
  setTimeout(() => {
    console.log('调用ElMessageBox.alert...')
    ElMessageBox.alert('这是一个测试警告对话框', '测试')
      .then(() => {
        console.log('ElMessageBox alert 确认')
        // 再测试confirm
        console.log('调用ElMessageBox.confirm...')
        return ElMessageBox.confirm('这是一个测试确认对话框', '测试')
      })
      .then(() => {
        console.log('ElMessageBox用户点击了确定')
        ElMessage.success('用户点击了确定')
      })
      .catch((error) => {
        console.log('ElMessageBox捕获到错误:', error)
        if (error === 'cancel') {
          ElMessage.info('用户点击了取消')
        } else {
          console.error('ElMessageBox错误:', error)
          ElMessage.error('ElMessageBox出错: ' + error)
        }
      })
  }, 1000)
}

// 创建工具
const handleCreateTool = async () => {
  console.log('=== 创建工具开始 ===')
  console.log('createFormRef存在:', !!createFormRef.value)

  if (!createFormRef.value) {
    console.error('createFormRef不存在')
    ElMessage.error('表单引用不存在')
    return
  }

  try {
    console.log('开始表单验证...')
    // 表单验证
    const valid = await createFormRef.value.validate()
    console.log('表单验证结果:', valid)

    console.log('表单数据:', createForm.value)
    const response = await createToolAPI(createForm.value)
    console.log('API响应:', response)

    if (response.data.status_code === 200) {
      ElMessage.success('工具创建成功')
      showCreateDialog.value = false
      resetCreateForm()
      fetchTools()
    } else {
      ElMessage.error(response.data.status_message || '创建工具失败')
    }
  } catch (error) {
    console.error('创建工具失败:', error)
    if (error !== false) { // 如果不是验证错误
      ElMessage.error('创建工具失败: ' + (error as Error).message)
    } else {
      ElMessage.error('表单验证失败')
    }
  }
}

// 编辑工具
const handleEditTool = async () => {
  console.log('=== 编辑工具开始 ===')
  console.log('editFormRef存在:', !!editFormRef.value)

  if (!editFormRef.value) {
    console.error('editFormRef不存在')
    ElMessage.error('表单引用不存在')
    return
  }

  try {
    console.log('开始表单验证...')
    // 表单验证
    const valid = await editFormRef.value.validate()
    console.log('表单验证结果:', valid)

    console.log('表单数据:', editForm.value)
    const response = await updateToolAPI(editForm.value)
    console.log('API响应:', response)

    if (response.data.status_code === 200) {
      ElMessage.success('工具更新成功')
      showEditDialog.value = false
      resetEditForm()
      fetchTools()
    } else {
      ElMessage.error(response.data.status_message || '更新工具失败')
    }
  } catch (error) {
    console.error('编辑工具失败:', error)
    if (error !== false) { // 如果不是验证错误
      ElMessage.error('编辑工具失败: ' + (error as Error).message)
    } else {
      ElMessage.error('表单验证失败')
    }
  }
}

// 删除工具
const handleDeleteTool = async (tool: Tool) => {
  console.log('=== 删除工具开始 ===')
  console.log('工具数据:', tool)

  // 系统工具不能删除
  if (tool.user_id === '0') {
    ElMessage.warning('系统工具不能删除')
    return
  }

  console.log('工具ID:', tool.tool_id)
  console.log('工具用户ID:', tool.user_id)

  // 使用自定义确认对话框
  showCustomDeleteConfirm(tool)
}

// 打开编辑对话框
const openEditDialog = (tool: Tool) => {
  console.log('=== 打开编辑对话框 ===')
  console.log('工具数据:', tool)
  currentTool.value = tool
  editForm.value = {
    tool_id: tool.tool_id,
    zh_name: tool.zh_name,
    en_name: tool.en_name,
    description: tool.description,
    logo_url: tool.logo_url
  }
  console.log('编辑表单数据:', editForm.value)
  showEditDialog.value = true
  console.log('showEditDialog设置为:', showEditDialog.value)
}

// 重置创建表单
const resetCreateForm = () => {
  createForm.value = {
    zh_name: '',
    en_name: '',
    description: '',
    logo_url: ''
  }
}

// 重置编辑表单
const resetEditForm = () => {
  editForm.value = {
    tool_id: '',
    zh_name: '',
    en_name: '',
    description: '',
    logo_url: ''
  }
  currentTool.value = null
}

// 切换标签页
const handleTabChange = () => {
  fetchTools()
}

// 刷新数据
const handleRefresh = () => {
  fetchTools()
}

// 格式化时间
const formatTime = (timeStr?: string) => {
  if (!timeStr) return ''
  return new Date(timeStr).toLocaleString('zh-CN')
}

onMounted(() => {
  userStore.initUserState()
  console.log('用户信息:', userStore.userInfo)
  console.log('当前用户ID:', userStore.userInfo?.id)
  console.log('是否登录:', userStore.isLoggedIn)
  fetchTools()
})
</script>

<template>
  <div class="tool-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h2>
          <img :src="pluginIcon" class="tool-icon" alt="Tool" />
          工具管理
        </h2>
        <p class="header-desc">管理和配置各种AI工具，提升对话体验</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" @click="handleRefresh" :loading="loading">
          刷新
        </el-button>
        <el-button type="primary" :icon="Plus" @click="testShowCreateDialog">
          创建工具
        </el-button>
        <el-button @click="testElMessageBox" type="warning">
          测试MessageBox
        </el-button>
      </div>
    </div>

    <!-- 标签页和搜索 -->
    <div class="tool-controls">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange" class="tool-tabs">
        <el-tab-pane label="全部工具" name="all">
          <template #label>
            <span class="tab-label">
              <View />
              全部工具
            </span>
          </template>
        </el-tab-pane>
        <el-tab-pane label="我的工具" name="own">
          <template #label>
            <span class="tab-label">
              <Edit />
              我的工具
            </span>
          </template>
        </el-tab-pane>
      </el-tabs>

      <div class="search-box">
        <el-input v-model="searchKeyword" placeholder="搜索工具名称或描述..." :prefix-icon="Search" clearable
          style="width: 300px" />
      </div>
    </div>

    <!-- 工具列表 -->
    <div class="tool-list" v-loading="loading">
      <div class="tool-grid">
        <div v-for="tool in filteredTools" :key="tool.tool_id" class="tool-card">
          <div class="tool-header">
            <div class="tool-icon">
              <img :src="tool.logo_url || '/src/assets/tool/default.png'" :alt="tool.zh_name"
                @error="(e) => { const target = e.target as HTMLImageElement; target.src = '/src/assets/tool/default.png' }" />
            </div>
            <div class="tool-actions">
              <el-button size="small" :icon="Edit" @click="openEditDialog(tool)" type="primary" class="edit-btn" text />
              <el-button v-if="isOwnTool(tool)" size="small" :icon="Delete" @click="handleDeleteTool(tool)"
                type="danger" class="delete-btn" />
            </div>
          </div>

          <div class="tool-info">
            <div class="tool-title">
              <h3 class="tool-name">{{ tool.zh_name }}</h3>
              <div v-if="tool.user_id === '0'" class="system-badge">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
                </svg>
                <span>系统工具</span>
              </div>
            </div>
            <p class="tool-description">{{ tool.description }}</p>

            <div class="tool-meta">
              <span class="tool-time">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <path
                    d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
                </svg>
                {{ formatTime(tool.create_time) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="filteredTools.length === 0 && !loading" class="empty-state">
        <div class="empty-icon">
          <i class="empty-icon-symbol">🛠️</i>
        </div>
        <h3>{{ searchKeyword ? '未找到匹配工具' : '暂无工具' }}</h3>
        <p v-if="searchKeyword">没有找到包含 "{{ searchKeyword }}" 的工具</p>
        <p v-else>添加工具可以让您的智能体拥有更多能力</p>
        <div class="empty-actions">
          <el-button v-if="searchKeyword" type="primary" @click="searchKeyword = ''">
            查看所有工具
          </el-button>
          <el-button v-else type="primary" @click="showCreateDialog = true">
            创建工具
          </el-button>
        </div>
      </div>
    </div>

    <!-- 创建工具对话框 -->
    <div v-if="showCreateDialog" class="custom-dialog-overlay" @click="showCreateDialog = false">
      <div class="custom-dialog" @click.stop>
        <div class="dialog-header">
          <h3>创建工具</h3>
          <button @click="showCreateDialog = false" class="close-btn">×</button>
        </div>

        <div class="dialog-body">
          <el-form ref="createFormRef" :model="createForm" :rules="createFormRules" label-width="100px">
            <el-form-item label="中文名称" prop="zh_name">
              <el-input v-model="createForm.zh_name" placeholder="请输入工具的中文名称" maxlength="20" show-word-limit />
            </el-form-item>

            <el-form-item label="英文名称" prop="en_name">
              <el-input v-model="createForm.en_name" placeholder="请输入工具的英文名称" maxlength="20" show-word-limit />
            </el-form-item>

            <el-form-item label="工具描述" prop="description">
              <el-input v-model="createForm.description" type="textarea" :rows="4" placeholder="请描述工具的功能和用途"
                maxlength="300" show-word-limit />
            </el-form-item>

            <el-form-item label="Logo URL" prop="logo_url">
              <el-input v-model="createForm.logo_url" placeholder="请输入工具Logo的URL地址" />
            </el-form-item>
          </el-form>
        </div>

        <div class="dialog-footer">
          <el-button @click="showCreateDialog = false">取消</el-button>
          <el-button type="primary" @click="handleCreateTool">创建</el-button>
        </div>
      </div>
    </div>

    <!-- 编辑工具对话框 -->
    <div v-if="showEditDialog" class="custom-dialog-overlay" @click="showEditDialog = false">
      <div class="custom-dialog" @click.stop>
        <div class="dialog-header">
          <h3>编辑工具</h3>
          <button @click="showEditDialog = false" class="close-btn">×</button>
        </div>

        <div class="dialog-body">
          <el-form ref="editFormRef" :model="editForm" :rules="editFormRules" label-width="100px">
            <el-form-item label="中文名称" prop="zh_name">
              <el-input v-model="editForm.zh_name" placeholder="请输入工具的中文名称" maxlength="50" show-word-limit />
            </el-form-item>

            <el-form-item label="英文名称" prop="en_name">
              <el-input v-model="editForm.en_name" placeholder="请输入工具的英文名称" maxlength="50" show-word-limit />
            </el-form-item>

            <el-form-item label="工具描述" prop="description">
              <el-input v-model="editForm.description" type="textarea" :rows="4" placeholder="请描述工具的功能和用途"
                maxlength="300" show-word-limit />
            </el-form-item>

            <el-form-item label="Logo URL" prop="logo_url">
              <el-input v-model="editForm.logo_url" placeholder="请输入工具Logo的URL地址" />
            </el-form-item>
          </el-form>
        </div>

        <div class="dialog-footer">
          <el-button @click="showEditDialog = false">取消</el-button>
          <el-button type="primary" @click="handleEditTool">保存</el-button>
        </div>
      </div>
    </div>

    <!-- 自定义删除确认对话框 -->
    <div v-if="showDeleteConfirm" class="custom-dialog-overlay" @click="cancelCustomDeleteConfirm">
      <div class="custom-dialog" @click.stop>
        <div class="dialog-header">
          <h3>确认删除</h3>
          <button @click="cancelCustomDeleteConfirm" class="close-btn">×</button>
        </div>

        <div class="dialog-body">
          <div class="delete-confirm-content">
            <div class="warning-icon">⚠️</div>
            <p class="delete-message">
              确定要删除工具 "{{ deleteConfirmTool?.zh_name }}" 吗？此操作不可恢复。
            </p>
            <p class="delete-hint">
              删除后，该工具将无法恢复，请谨慎操作。
            </p>
          </div>
        </div>

        <div class="dialog-footer">
          <el-button @click="cancelCustomDeleteConfirm">取消</el-button>
          <el-button type="danger" @click="handleCustomDeleteConfirm">删除</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.tool-page {
  padding: 24px;
  height: 100%;
  background: #f5f7fa;

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 24px;
    padding: 24px;
    background: white;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);

    .header-left {
      h2 {
        margin: 0 0 8px 0;
        font-size: 28px;
        font-weight: 600;
        color: #3a7be2; // 修改颜色为蓝色，与插件图标相似
        display: flex;
        align-items: center;
        gap: 12px;
        background: linear-gradient(90deg, #3a7be2, #4a66b3); // 添加渐变效果
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;

        .tool-icon {
          width: 32px;
          height: 32px;
        }
      }

      .header-desc {
        margin: 0;
        color: #4a66b3; // 修改描述文字颜色，与标题相协调
        font-size: 14px;
        opacity: 0.9;
      }
    }

    .header-actions {
      display: flex;
      gap: 12px;
    }
  }

  .tool-controls {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    padding: 0 4px;

    .tool-tabs {
      :deep(.el-tabs__header) {
        margin: 0;
      }

      :deep(.el-tabs__nav-wrap) {
        padding: 0;
      }

      .tab-label {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 14px;
      }
    }

    .search-box {
      display: flex;
      align-items: center;
    }
  }

  .tool-list {
    .tool-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
      gap: 20px;

      .tool-card {
        background: white;
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
        border: 1px solid #e8eaed;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;



        &::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 4px;
          background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
          opacity: 0;
          transition: opacity 0.3s ease;
        }

        &:hover {
          transform: translateY(-4px);
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
          border-color: #d0d7de;

          &::before {
            opacity: 1;
          }
        }

        .tool-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 20px;

          .tool-icon {
            width: 56px;
            height: 56px;
            border-radius: 12px;
            overflow: hidden;
            background: #f8f9fa;
            border: 2px solid #e8eaed;

            img {
              width: 100%;
              height: 100%;
              object-fit: cover;
            }
          }

          .tool-actions {
            display: flex;
            gap: 8px;
            opacity: 1;
            transform: translateY(0);
            transition: all 0.3s ease;

            .edit-btn {
              background: rgba(64, 158, 255, 0.1) !important;
              border: 1px solid rgba(64, 158, 255, 0.2) !important;
              color: #409eff !important;
              border-radius: 8px;
              transition: all 0.3s ease;

              &:hover {
                background: rgba(64, 158, 255, 0.2) !important;
                border-color: rgba(64, 158, 255, 0.3) !important;
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(64, 158, 255, 0.2);
              }
            }

            .delete-btn {
              background: rgba(245, 108, 108, 0.1) !important;
              border: 1px solid rgba(245, 108, 108, 0.2) !important;
              color: #f56c6c !important;
              border-radius: 8px;
              transition: all 0.3s ease;

              &:hover {
                background: rgba(245, 108, 108, 0.2) !important;
                border-color: rgba(245, 108, 108, 0.3) !important;
                color: #f56c6c !important;
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(245, 108, 108, 0.2);
              }
            }
          }
        }

        .tool-info {
          .tool-title {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;

            .tool-name {
              font-size: 20px;
              font-weight: 600;
              color: #1a1a1a;
              margin: 0;
              line-height: 1.3;
            }

            .system-badge {
              display: flex;
              align-items: center;
              gap: 4px;
              padding: 4px 10px;
              background: rgba(14, 165, 233, 0.1);
              color: #0ea5e9;
              border: 1px solid rgba(14, 165, 233, 0.2);
              border-radius: 20px;
              font-size: 11px;
              font-weight: 600;
              letter-spacing: 0.5px;

              svg {
                width: 12px;
                height: 12px;
              }
            }
          }



          .tool-description {
            color: #666;
            font-size: 14px;
            line-height: 1.6;
            margin: 0 0 16px 0;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
          }

          .tool-meta {
            .tool-time {
              font-size: 12px;
              color: #666;
              display: flex;
              align-items: center;
              gap: 4px;

              svg {
                color: #999;
              }
            }
          }
        }
      }
    }

    .empty-state {
      text-align: center;
      padding: 80px 20px;
      color: #666;

      .empty-icon {
        margin-bottom: 24px;

        img {
          width: 200px;
          height: auto;
          opacity: 0.6;
        }
      }

      h3 {
        margin: 0 0 12px 0;
        font-size: 20px;
        font-weight: 500;
        color: #333;
      }

      p {
        margin: 0;
        font-size: 14px;
        line-height: 1.5;
      }
    }
  }
}

/* 空状态样式 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
  margin: 20px auto;
  max-width: 600px;

  .empty-icon {
    width: 120px;
    height: 120px;
    display: flex;
    justify-content: center;
    align-items: center;
    background: rgba(64, 158, 255, 0.1);
    border-radius: 50%;
    margin-bottom: 20px;

    .empty-icon-symbol {
      font-size: 60px;
    }
  }

  h3 {
    font-size: 20px;
    color: #303133;
    margin: 0 0 16px;
  }

  p {
    margin: 0 0 20px;
    font-size: 16px;
    color: #909399;
    max-width: 300px;
  }

  .empty-actions {
    display: flex;
    gap: 12px;
  }
}

// 响应式设计
@media (max-width: 768px) {
  .tool-page {
    padding: 16px;

    .page-header {
      flex-direction: column;
      gap: 16px;
      align-items: stretch;

      .header-actions {
        justify-content: flex-end;
      }
    }

    .tool-controls {
      flex-direction: column;
      gap: 16px;
      align-items: stretch;

      .search-box {
        justify-content: stretch;

        .el-input {
          width: 100%;
        }
      }
    }

    .tool-list .tool-grid {
      grid-template-columns: 1fr;
    }
  }
}

/* 自定义对话框样式 */
.custom-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 2000;
}

.custom-dialog {
  background: white;
  border-radius: 12px;
  width: 600px;
  max-width: 90vw;
  max-height: 90vh;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e8eaed;

  h3 {
    margin: 0;
    font-size: 18px;
    font-weight: 500;
    color: #333;
  }

  .close-btn {
    background: none;
    border: none;
    font-size: 24px;
    cursor: pointer;
    color: #999;
    padding: 0;
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;

    &:hover {
      background-color: #f5f5f5;
      color: #666;
    }
  }
}

.dialog-body {
  padding: 24px;
  max-height: 60vh;
  overflow-y: auto;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid #e8eaed;
  background-color: #fafbfc;
}

/* 删除确认对话框样式 */
.delete-confirm-content {
  text-align: center;
  padding: 20px 0;

  .warning-icon {
    font-size: 48px;
    margin-bottom: 16px;
    color: #e6a23c;
  }

  .delete-message {
    font-size: 16px;
    color: #333;
    margin-bottom: 12px;
    line-height: 1.5;
  }

  .delete-hint {
    font-size: 14px;
    color: #999;
    line-height: 1.4;
  }
}
</style>