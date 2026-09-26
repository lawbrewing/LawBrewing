document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('menu-container');

    fetch('menu.json')
        .then(response => response.json())
        .then(menuData => {
            container.innerHTML = ''; // Clear loading state
            
            menuData.drinks.forEach(drink => {
                const ingredientsHTML = drink.syrups.map(item => `
                    <li class="flex items-start text-sm text-sand-200/90 mb-1.5">
                        <svg class="w-4 h-4 text-lagoon-teal mr-2 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                        </svg>
                        <span>${item}</span>
                    </li>
                `).join('');

                const cardHTML = `
                    <div class="glass-card rounded-2xl p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-lagoon-teal/10 flex flex-col h-full group">
                        <div class="mb-4">
                            <h3 class="text-xl font-serif text-lagoon-foam mb-1 group-hover:text-lagoon-teal transition-colors duration-300">${drink.name}</h3>
                            <p class="text-xs text-sand-300/70 italic">${drink.description}</p>
                        </div>
                        
                        <div class="mt-auto pt-4 border-t border-lagoon-teal/20">
                            <h4 class="text-xs uppercase tracking-wider text-lagoon-teal font-semibold mb-3">Composition</h4>
                            <ul class="space-y-1">
                                ${ingredientsHTML}
                            </ul>
                        </div>
                    </div>
                `;
                
                container.innerHTML += cardHTML;
            });
        })
        .catch(error => {
            console.error('Error fetching menu:', error);
            container.innerHTML = '<p class="text-sand-300 text-center w-full">The menu is drifting out to sea. Please check back later.</p>';
        });
});
