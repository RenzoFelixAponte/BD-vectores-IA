import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // El destino del backend vive SOLO en frontend/.env (VITE_API_URL).
  // El cliente llama directo a esa URL (el backend tiene CORS abierto),
  // por eso ya no se define el puerto aquí ni se usa proxy.
  server: {
    port: 5173,
  },
});
