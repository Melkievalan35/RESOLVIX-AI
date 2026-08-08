import api from "./api";

export async function login(email, password) {
  const data = new URLSearchParams();

  data.append("username", email);
  data.append("password", password);
  data.append("grant_type", "password");

  const res = await api.post("/auth/login", data, {
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
  });

  localStorage.setItem("token", res.data.access_token);
  localStorage.setItem("user", JSON.stringify(res.data.user));

  return res.data;
}

export async function register(data) {
  const res = await api.post("/auth/register", data);
  return res.data;
}

export function logout() {
  localStorage.clear();
}

export function getUser() {
  return JSON.parse(localStorage.getItem("user"));
}

export function isLoggedIn() {
  return localStorage.getItem("token") !== null;
}