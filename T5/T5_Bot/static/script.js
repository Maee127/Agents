function submitForm(action) {
    const formData = new FormData();
    const inputText = document.getElementById("inputText").value;
    
    // Validate input
    if (!inputText.trim()) {
        alert("Please enter some text to process.");
        return;
    }
    
    formData.append("inputText", inputText);
    formData.append("sourceLanguage", document.getElementById("sourceLanguage").value);
    formData.append("targetLanguage", document.getElementById("targetLanguage").value);

    // Fix: Check for the correct action name
    if (action === "summarize" || action === "translate-summary") {
        const summaryText = document.getElementById("summaryText").value;
        formData.append("summaryText", summaryText);
    }
    
    fetch("http://127.0.0.1:5000/" + action, {
        method: "POST",
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.text();
    })
    .then(data => {
        if (action === "summarize") {
            document.getElementById("summaryText").value = data;
        } else if (action === "translate-summary") {
            document.getElementById("translatedSummaryText").value = data;
        } else if (action === "translate") {
            document.getElementById("translatedText").value = data;
        }
    })
    .catch(error => {
        console.error("Error:", error);
        alert("An error occurred. Please check the console for details.");
    });
}