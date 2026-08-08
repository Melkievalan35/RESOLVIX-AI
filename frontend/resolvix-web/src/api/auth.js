import api from "./api";

export const login = async (email, password) => {

    const form = new URLSearchParams();

    form.append("username", email);
    form.append("password", password);

    const response = await api.post(
        "/auth/login",
        form,
        {
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
            },
        }
    );

    return response.data;
};

export const register = async (user) => {

    const response = await api.post(
        "/auth/register",
        user
    );

    return response.data;
};