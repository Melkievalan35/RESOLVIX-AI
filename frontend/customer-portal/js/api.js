const API = "http://127.0.0.1:8000";

async function apiRequest(endpoint, method = "GET", body = null) {

    const token = localStorage.getItem("token");

    const options = {
        method,
        headers: {
            "Content-Type": "application/json"
        }
    };

    if (token) {
        options.headers["Authorization"] = `Bearer ${token}`;
    }

    if (body) {
        options.body = JSON.stringify(body);
    }

    const response = await fetch(API + endpoint, options);

    if (!response.ok) {
        throw await response.json();
    }

    return await response.json();
}