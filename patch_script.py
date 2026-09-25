content = open("static/script.js").read()

old1 = 'row.innerHTML = html;\n  chatWindow.appendChild(row);\n  const toggle = row.querySelector(".citations-toggle");'
new1 = 'row.innerHTML = html;\n  chatWindow.appendChild(row);\n  if (window.__lastUserQuestion) addRegenerateButton(row, window.__lastUserQuestion, document.getElementById("opt-multi-query").checked, document.getElementById("opt-compression").checked, window.__lastDocScope);\n  const toggle = row.querySelector(".citations-toggle");'

old2 = 'const question = input.value.trim();\n  if (!question) return;\n  if (activeChatController)'
new2 = 'const question = input.value.trim();\n  if (!question) return;\n  window.__lastUserQuestion = question;\n  if (activeChatController)'

if old1 in content:
    content = content.replace(old1, new1)
    print("Patch 1 applied.")
else:
    print("Patch 1 pattern NOT found — no change made.")

if old2 in content:
    content = content.replace(old2, new2)
    print("Patch 2 applied.")
else:
    print("Patch 2 pattern NOT found — no change made.")

open("static/script.js", "w").write(content)
