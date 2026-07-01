// Auto-dismiss alerts after 4s
document.querySelectorAll('.alert-dismissible').forEach(el => {
  setTimeout(() => {
    const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
    if (bsAlert) bsAlert.close();
  }, 4000);
});

// On new project form: sync merchant name from project name if merchant name is blank
const nameInput = document.querySelector('input[name="name"]');
const merchantInput = document.querySelector('input[name="merchant_name"]');
if (nameInput && merchantInput) {
  let merchantTouched = false;
  merchantInput.addEventListener('input', () => { merchantTouched = true; });
  nameInput.addEventListener('input', () => {
    if (!merchantTouched) merchantInput.value = nameInput.value;
  });
}
