const loginForm = document.getElementById("loginForm");
const errorMessage = document.getElementById("errorMessage");
const signInButton = document.getElementById("signInButton");


loginForm.addEventListener("submit", async (event) => {

    event.preventDefault();

    errorMessage.textContent = "";

    const username =
        document.getElementById("username").value.trim();

    const password =
        document.getElementById("password").value;

    signInButton.disabled = true;
    signInButton.textContent = "Signing In...";

    try {

        const response = await fetch(
            "/api/auth/login",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    username,
                    password
                })
            }
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.detail ||
                "Invalid username or password"
            );
        }

        sessionStorage.setItem(
            "access_token",
            data.access_token
        );

        sessionStorage.setItem(
            "token_type",
            data.token_type
        );

        window.location.href = "/dashboard";

    } catch (error) {

        errorMessage.textContent =
            error.message;

    } finally {

        signInButton.disabled = false;
        signInButton.textContent = "Sign In";
    }
});