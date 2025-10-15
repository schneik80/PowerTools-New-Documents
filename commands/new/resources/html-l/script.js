const tabs = document.querySelectorAll('.navtab')
const contents = document.querySelectorAll('.content')
const underline = document.querySelector('.underline')

function updateUnderline () {
  const activeTab = document.querySelector('.navtab.active')
  underline.style.width = `${activeTab.offsetWidth}px`
  underline.style.left = `${activeTab.offsetLeft}px`
}

tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    tabs.forEach(t => t.classList.remove('active'))
    tab.classList.add('active')
    const target = tab.getAttribute('data-target')
    contents.forEach(content => {
      if (content.id === target) {
        content.classList.add('active')
      } else {
        content.classList.remove('active')
      }
    })
    updateUnderline()
  })
})

// Add hover overlay effects
function initializeHoverEffects () {
  const containers = document.querySelectorAll('.container')

  containers.forEach(container => {
    container.addEventListener('mouseenter', function () {
      this.classList.add('hovering')
    })

    container.addEventListener('mouseleave', function () {
      this.classList.remove('hovering', 'hover-left', 'hover-right')
    })

    container.addEventListener('mousemove', function (e) {
      if (!this.classList.contains('hovering')) return

      const rect = this.getBoundingClientRect()
      const mouseX = e.clientX - rect.left
      const containerWidth = rect.width
      const halfWidth = containerWidth / 2

      // Remove previous hover classes
      this.classList.remove('hover-left', 'hover-right')

      // Add appropriate hover class based on mouse position
      if (mouseX < halfWidth) {
        this.classList.add('hover-left')
      } else {
        this.classList.add('hover-right')
      }
    })
  })
}

window.addEventListener('resize', updateUnderline)
updateUnderline()

// Initialize hover effects when DOM is loaded
document.addEventListener('DOMContentLoaded', initializeHoverEffects)

// Also initialize immediately in case DOM is already loaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeHoverEffects)
} else {
  initializeHoverEffects()
}
