import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
    plugins: [react(), tailwindcss()],
    server: {
        port: 3000,
        proxy: {
            '/api': 'http://localhost:8000',
            '/ws': {
                target: 'ws://localhost:8000',
                ws: true,
            },
            '/uploads': 'http://localhost:8000',
            '/face_data': 'http://localhost:8000',
            '/danger_zone_images': 'http://localhost:8000',
        },
    },
})
