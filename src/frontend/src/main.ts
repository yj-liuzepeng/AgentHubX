import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './router';
import { createPinia } from 'pinia'
import persistState from 'pinia-plugin-persistedstate';
import ElementPlus from 'element-plus'

// Element Plus CSS
import 'element-plus/dist/index.css'

const app = createApp(App)
const pinia = createPinia();
pinia.use(persistState);

app.use(router);
app.use(pinia);
app.use(ElementPlus); // 注册Element Plus
app.mount('#app')
