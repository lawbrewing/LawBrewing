document.addEventListener('DOMContentLoaded', () => {
    const menuContainer = document.getElementById('menu-container');

    // Fetch the JSON file
    fetch('menu.json')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            renderMenu(data.drinks);
        })
        .catch(error => {
            console.error('Error fetching menu:', error);
            menuContainer.innerHTML = '<p>The menu is currently drifting out to sea. Please check back later.</p>';
        });

    function renderMenu(drinks) {
        // Clear any loading text
        menuContainer.innerHTML = '';

        drinks.forEach(drink => {
            // Create card container
            const card = document.createElement('div');
            card.className = 'drink-card';

            // Create drink name
            const nameEl = document.createElement('h2');
            nameEl.className = 'drink-name';
            nameEl.textContent = drink.name;

            // Create drink description
            const descEl = document.createElement('p');
            descEl.className = 'drink-desc';
            descEl.textContent = drink.description;

            // Create ingredients list
            const ingredientsList = document.createElement('ul');
            ingredientsList.className = 'drink-ingredients';
            
            drink.ingredients.forEach(ingredient => {
                const li = document.createElement('li');
                li.textContent = ingredient;
                ingredientsList.appendChild(li);
            });

            // Append elements to card, then card to container
            card.appendChild(nameEl);
            card.appendChild(descEl);
            card.appendChild(ingredientsList);
            menuContainer.appendChild(card);
        });
    }
});
