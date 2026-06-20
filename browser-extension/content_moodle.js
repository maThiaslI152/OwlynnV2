(function extractMoodleContext() {
  function isMoodle() {
    return document.querySelector('meta[name="moodle-version"]') !== null ||
           document.body.classList.contains('moodle-has-zindex') ||
           document.querySelector('#page-site-index.moodle-has-zindex') !== null ||
           document.querySelector('.course-content') !== null;
  }

  if (!isMoodle()) {
    return { isMoodle: false };
  }

  const maxText = 12000;
  const maxSelection = 4000;
  const selection = window.getSelection ? window.getSelection().toString() : "";
  
  let text = "";
  // Prioritize the main content area of Moodle to strip out navbars and side blocks
  const regionMain = document.querySelector('#region-main') || document.querySelector('[role="main"]');
  if (regionMain) {
    text = regionMain.innerText;
  } else {
    text = document.body ? document.body.innerText : "";
  }

  // Look for course-specific structured data (e.g. assignments, modules)
  let structuredData = [];
  document.querySelectorAll('.activity').forEach(activity => {
    const nameNode = activity.querySelector('.instancename');
    const linkNode = activity.querySelector('a');
    
    if (nameNode) {
      let activityText = nameNode.innerText.replace(/\n/g, ' ').trim();
      if (linkNode && linkNode.href) {
        structuredData.push(`- [${activityText}](${linkNode.href})`);
      } else {
        structuredData.push("- " + activityText);
      }
    }
  });

  // Look for Moodle Quiz Questions
  const questions = document.querySelectorAll('.que');
  if (questions.length > 0) {
    structuredData.push("\n== Moodle Quiz Questions (Interactive) ==");
    questions.forEach((q, index) => {
      const qtext = q.querySelector('.qtext') ? q.querySelector('.qtext').innerText.trim() : `Question ${index+1}`;
      structuredData.push(`\n[Q] ${qtext}`);
      
      const answers = q.querySelectorAll('.answer input[type="radio"], .answer input[type="checkbox"]');
      answers.forEach(input => {
        let labelText = "";
        if (input.id) {
          const label = q.querySelector(`label[for="${input.id}"]`);
          if (label) labelText = label.innerText.trim();
        }
        if (!labelText && input.parentElement) {
          labelText = input.parentElement.innerText.replace(input.value, '').trim();
        }
        structuredData.push(`  - Choice: ${labelText} (Selector: input[name="${input.name}"][value="${input.value}"])`);
      });
    });
    
    const nextBtn = document.querySelector('input[name="next"], button[name="next"], input[value="Next page"], input[value="Finish attempt ..."]');
    if (nextBtn) {
      let selector = nextBtn.tagName.toLowerCase();
      if (nextBtn.name) selector += `[name="${nextBtn.name}"]`;
      else if (nextBtn.value) selector += `[value="${nextBtn.value}"]`;
      structuredData.push(`\n[Next Button Selector: ${selector}]`);
    }
  }

  if (structuredData.length > 0) {
    text = "== Course Modules/Activities ==\n" + structuredData.join("\n") + "\n\n== Main Content ==\n" + text;
  }

  return {
    isMoodle: true,
    title: document.title || "",
    url: location.href || "",
    text: text.slice(0, maxText),
    selection: selection.slice(0, maxSelection),
  };
})();
