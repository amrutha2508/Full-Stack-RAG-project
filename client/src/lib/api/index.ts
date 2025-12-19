
// API Configuration

const API_BASE_URL = process.env.NEXT_BASE_URL || "http://localhost:8000"

export const apiClient = {
    get: async (endpoint: string, token?:string | null) => {
        const headers:HeadersInit = {};
        if(token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        // below is calling the backend server projects.py
        const response = await fetch(`${API_BASE_URL}${endpoint}`,{
            headers
        });
        if(!response.ok){
            throw new Error(`API Error:${response.status}`);
        }
        return response.json();
    },
    post: async(endpoint:string, data:any, token?:string | null) => {
        const headers:HeadersInit = {
            "Content-type":"application/json", 
        }
        if(token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        const response = await fetch(`${API_BASE_URL}${endpoint}`,{
            method:"POST",
            headers,
            body:JSON.stringify(data)
        })
        if(!response.ok){
            throw new Error(`API Error:${response.status}`);
        }
        return response.json();
    },
    delete: async(endpoint: string, token?:string | null) => {
        const headers:HeadersInit = {};
        if(token){
            headers["Authorization"] = `Bearer ${token}`;
        }
        const response = await fetch(`${API_BASE_URL}${endpoint}`,{
            method:"DELETE",
            headers
        })
        if (!response.ok){
            throw new Error(`API Error:${response.status}`);
        }
          return response.json();
    }
}
