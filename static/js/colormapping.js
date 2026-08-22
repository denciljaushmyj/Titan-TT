document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("#order-listing tbody tr").forEach(function (row) {
    var cell = row.children[4];
    if (!cell) return;

    var colorText = (cell.textContent || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
    console.log("Normalized colorText:", colorText);

    if (!colorText || colorText === "n/a") return;

    var colorMap = {
      black: {
        bg: "linear-gradient(135deg, #222 60%, #555 100%)",
        border: "#888",
      },
      ips: {
        bg: "linear-gradient(135deg, #e0e0e0 60%, #bdbdbd 100%)",
        border: "#757575",
      },
      ipg: {
        bg: "linear-gradient(135deg, #ffd700 60%, #ffe066 100%)",
        border: "#bfa600",
      },
      "ip-gun": {
        bg: "linear-gradient(135deg, #4b4b4b 60%, #a6a6a6 100%)",
        border: "#333",
      },
      "ip-brown": {
        bg: "linear-gradient(135deg, #b97a56 60%, #ffe066 100%)",
        border: "#8d5524",
      },
      rg: {
        bg: "linear-gradient(135deg, #e3a6a1 60%, #f7cac9 100%)",
        border: "#b76e79",
      },
      ipsipg: {
        bg: "linear-gradient(135deg, #e0e0e0 60%, #ffd700 100%)",
        border: "#757575",
      },
      "ip-blue m": {
        bg: "linear-gradient(135deg, #0074d9 60%, #7fdbff 100%)",
        border: "#00509e",
      },
      "ipsipg-2n": {
        bg: "linear-gradient(135deg, #ffe066 60%, #ffd700 100%)",
        border: "#bfa600",
      },
      "rg-bi": {
        bg: "linear-gradient(135deg, #e3a6a1 60%, #f7cac9 100%)",
        border: "#b76e79",
      },
      "ipg-2n": {
        bg: "linear-gradient(135deg, #ffe066 60%, #ffd700 100%)",
        border: "#bfa600",
      },
      "ipsipg-hn": {
        bg: "linear-gradient(135deg, #e0e0e0 60%, #ffd700 100%)",
        border: "#757575",
      },
      "ip-corn.gold": {
        bg: "linear-gradient(135deg, #ffd700 60%, #ffcc00 100%)",
        border: "#bfa600",
      },
      "ip-titanium": {
        bg: "linear-gradient(135deg, #8a8a8a 60%, #bdbdbd 100%)",
        border: "#666",
      },
      "ipg-half.n": {
        bg: "linear-gradient(135deg, #ffe066 60%, #ffd700 100%)",
        border: "#bfa600",
      },
      anodising: {
        bg: "linear-gradient(135deg, #ff7f50 60%, #ff4500 100%)",
        border: "#cc3700",
      },
      "ip-blue inh": {
        bg: "linear-gradient(135deg, #0074d9 60%, #7fdbff 100%)",
        border: "#00509e",
      },
      "ip-blue": {
        bg: "linear-gradient(135deg, #0074d9 60%, #7fdbff 100%)",
        border: "#00509e",
      },
      "ip-br anti": {
        bg: "linear-gradient(135deg, #b97a56 60%, #8d5524 100%)",
        border: "#8d5524",
      },
      "ip-bronze": {
        bg: "linear-gradient(135deg, #cd7f32 60%, #d2b48c 100%)",
        border: "#8b4513",
      },
      "ip-ch.gold": {
        bg: "linear-gradient(135deg, #ffd700 60%, #ffcc00 100%)",
        border: "#bfa600",
      },
      "ip-sil anti": {
        bg: "linear-gradient(135deg, #c0c0c0 60%, #f5f5f5 100%)",
        border: "#888",
      },
      "ip-lcr": {
        bg: "linear-gradient(135deg, #ff4500 60%, #ff6347 100%)",
        border: "#cc3700",
      },
      "ip-ogr": {
        bg: "linear-gradient(135deg, #228b22 60%, #32cd32 100%)",
        border: "#006400",
      },
      "ip-ice blue": {
        bg: "linear-gradient(135deg, #0074d9 60%, #7fdbff 100%)",
        border: "#00509e",
      },
      "ip-plum": {
        bg: "linear-gradient(135deg, #dda0dd 60%, #ee82ee 100%)",
        border: "#800080",
      },
      "ip-titanium blue": {
        bg: "linear-gradient(135deg, #4682b4 60%, #5f9ea0 100%)",
        border: "#2c5d72",
      },
    };

    var match = Object.keys(colorMap).find(function (key) {
      return colorText === key || colorText.includes(key);
    });
    console.log("Matched key:", match);

    var oldCircle = cell.querySelector(".plating-color-indicator");
    if (oldCircle) oldCircle.remove();

    if (match) {
      console.log("Creating indicator for:", match);
      var style = colorMap[match];
      var circle = document.createElement("span");
      circle.className = "plating-color-indicator";
      circle.style.display = "inline-block";
      circle.style.width = "16px";
      circle.style.height = "16px";
      circle.style.borderRadius = "50%";
      circle.style.marginRight = "6px";
      circle.style.verticalAlign = "middle";
      if (style.bg.startsWith("linear-gradient")) {
        circle.style.background = "";
        circle.style.backgroundImage = style.bg;
      } else {
        circle.style.background = style.bg;
      }
      circle.style.border = "2px solid " + style.border;
      cell.insertBefore(circle, cell.firstChild);
    }
  });
});