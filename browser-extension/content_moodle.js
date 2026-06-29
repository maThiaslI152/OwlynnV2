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
    structuredData.push(`Total Questions: ${questions.length}`);
    questions.forEach((q, index) => {
      const qtext = q.querySelector('.qtext') ? q.querySelector('.qtext').innerText.trim() : `Question ${index+1}`;
      structuredData.push(`\n[Q${index+1}] ${qtext}`);
      
      const answers = q.querySelectorAll('.answer input[type="radio"], .answer input[type="checkbox"]');
      answers.forEach(input => {
        let labelText = "";
        if (input.id) {
          const safeId = CSS.escape ? CSS.escape(input.id) : input.id.replace(/"/g, '\\"');
          const label = q.querySelector(`label[for="${safeId}"]`);
          if (label) labelText = label.innerText.trim();
        }
        if (!labelText && input.parentElement) {
          labelText = input.parentElement.innerText.replace(input.value, '').trim();
        }
        const safeName = CSS.escape ? CSS.escape(input.name || '') : (input.name || '').replace(/"/g, '\\"');
        const safeValue = CSS.escape ? CSS.escape(input.value || '') : (input.value || '').replace(/"/g, '\\"');
        structuredData.push(`  - Choice: ${labelText} (Selector: input[name="${safeName}"][value="${safeValue}"])`);
      });
    });
    
    const nextBtn = document.querySelector('input[name="next"], button[name="next"], input[value="Next page"], input[value="Finish attempt ..."]');
    if (nextBtn) {
      let selector = nextBtn.tagName.toLowerCase();
      if (nextBtn.name) selector += `[name="${CSS.escape ? CSS.escape(nextBtn.name) : nextBtn.name.replace(/"/g, '\\"')}"]`;
      else if (nextBtn.value) selector += `[value="${CSS.escape ? CSS.escape(nextBtn.value) : nextBtn.value.replace(/"/g, '\\"')}"]`;
      structuredData.push(`\n[Next Button Selector: ${selector}]`);
    }
  }

  // ── Phase 3: Additional Moodle Extractions ─────────────────────────

  // 3.1 Grades Extraction
  const gradeTable = document.querySelector('.gradestable') || document.querySelector('#user-grades') || document.querySelector('.generaltable');
  if (gradeTable) {
    structuredData.push("\n== Grades ==");
    const rows = gradeTable.querySelectorAll('tr');
    rows.forEach(row => {
      const cells = row.querySelectorAll('td, th');
      if (cells.length >= 2) {
        const item = cells[0]?.innerText?.trim();
        const grade = cells[1]?.innerText?.trim();
        if (item && grade) {
          structuredData.push(`- ${item}: ${grade}`);
        }
      }
    });
  }

  // 3.2 Course Sections
  const sections = document.querySelectorAll('.section, .section-summary, .course-section');
  if (sections.length > 0) {
    structuredData.push("\n== Course Sections ==");
    sections.forEach((section, index) => {
      const sectionName = section.querySelector('.sectionname, .section-title, h3');
      const sectionInfo = section.querySelector('.section-info, .section-summary-text');
      const activities = section.querySelectorAll('.activity');
      
      let sectionText = sectionName ? sectionName.innerText.trim() : `Section ${index + 1}`;
      if (sectionInfo) sectionText += ` — ${sectionInfo.innerText.trim()}`;
      structuredData.push(`\n[Section] ${sectionText}`);
      
      if (activities.length > 0) {
        activities.forEach(activity => {
          const name = activity.querySelector('.instancename');
          const link = activity.querySelector('a');
          if (name) {
            let actText = name.innerText.trim();
            if (link && link.href) actText = `[${actText}](${link.href})`;
            structuredData.push(`  - ${actText}`);
          }
        });
      }
    });
  }

  // 3.3 Assignment Details
  const assignments = document.querySelectorAll('.assignsubmission, .modtype_assign, .assignment');
  if (assignments.length > 0) {
    structuredData.push("\n== Assignments ==");
    assignments.forEach(assign => {
      const title = assign.querySelector('.instancename, .assignment-name, h3');
      const dueDate = assign.querySelector('.duedate, .assign-due-date, [data-region="due-date"]');
      const status = assign.querySelector('.submissionstatus, .submission-status, [data-region="submission-status"]');
      const link = assign.querySelector('a');
      
      let assignText = title ? title.innerText.trim() : 'Assignment';
      if (link && link.href) assignText = `[${assignText}](${link.href})`;
      structuredData.push(`\n[Assignment] ${assignText}`);
      if (dueDate) structuredData.push(`  Due: ${dueDate.innerText.trim()}`);
      if (status) structuredData.push(`  Status: ${status.innerText.trim()}`);
    });
  }

  // 3.4 File Download Links
  const fileResources = document.querySelectorAll('.resource a[href], .modtype_resource a[href], .modtype_folder a[href], a[href*="pluginfile.php"], a[href*="webservice/pluginfile"]');
  if (fileResources.length > 0) {
    structuredData.push("\n== Downloadable Files ==");
    fileResources.forEach(link => {
      const fileName = link.innerText.trim() || link.getAttribute('download') || link.href.split('/').pop();
      const fileUrl = link.href;
      if (fileUrl && !fileUrl.includes('#') && fileName) {
        structuredData.push(`- [${fileName}](${fileUrl})`);
      }
    });
  }

  // 3.5 Quiz Navigation
  const quizNav = document.querySelector('.qn_buttons, .mod_quiz-navigation, [data-region="block_navigation"]');
  if (quizNav) {
    structuredData.push("\n== Quiz Navigation ==");
    const navButtons = quizNav.querySelectorAll('.qnbutton, .mod_quiz-next-nav, button, a');
    let totalQuestions = 0;
    navButtons.forEach(btn => {
      const text = btn.innerText.trim();
      const href = btn.getAttribute('href');
      if (text.match(/^\d+$/)) totalQuestions++;
      if (href) {
        structuredData.push(`- [${text}](${href})`);
      } else {
        structuredData.push(`- ${text}`);
      }
    });
    if (totalQuestions > 0) {
      structuredData.unshift(`Total Quiz Questions: ${totalQuestions}`);
    }
  }

  // 3.6 User Profile
  const userProfile = document.querySelector('.userprofile, .user-info, [data-region="user-info"]');
  if (userProfile) {
    structuredData.push("\n== User Profile ==");
    const userName = userProfile.querySelector('.username, .user-name, h1, h2');
    const userEmail = userProfile.querySelector('.email, .user-email, [data-region="email"]');
    const userPicture = userProfile.querySelector('img.userpicture, img.avatar');
    
    if (userName) structuredData.push(`Name: ${userName.innerText.trim()}`);
    if (userEmail) structuredData.push(`Email: ${userEmail.innerText.trim()}`);
    if (userPicture) structuredData.push(`Avatar: ${userPicture.src}`);
  }

  if (structuredData.length > 0) {
    text = structuredData.join("\n") + "\n\n== Main Content ==\n" + text;
  }

  return {
    isMoodle: true,
    title: document.title || "",
    url: location.href || "",
    text: text.slice(0, maxText),
    selection: selection.slice(0, maxSelection),
  };
})();
