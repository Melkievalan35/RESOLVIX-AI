import api from "./api";

export async function getComplaints() {
  const res = await api.get("/complaints");
  return res.data;
}

export async function createComplaint(data) {
  const res = await api.post("/complaints", data);
  return res.data;
}